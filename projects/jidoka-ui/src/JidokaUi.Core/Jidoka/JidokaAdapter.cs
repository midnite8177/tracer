using System.Text.Json;
using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Jidoka;

/// <summary>
/// The one layer that starts jidoka's scripts. A metadata key that jidoka owns, such as the gate's
/// decision or an epic's factory rules, has one writer, which is the script, so the app changes it
/// only here and never through <see cref="BdAdapter"/>. See ADR 0018.
/// </summary>
public sealed class JidokaAdapter
{
    /// <summary>How long the app waits for a script that makes a few writes, before it gives up on it.</summary>
    public static readonly TimeSpan WaitLimit = TimeSpan.FromMinutes(2);

    /// <summary>How long the app waits for a script that may run the full suite of the repository.</summary>
    public static readonly TimeSpan FullSuiteWaitLimit = TimeSpan.FromMinutes(30);

    private const string GateScript = "gate.py";
    private const string RulesScript = "rules.py";
    private const string FactoryStateScript = "factory_state.py";
    private const string SchedulerScript = "scheduler.py";
    private const string AbandonedWriteMessage =
        "The script has not answered. The app does not stop a script that writes, so it may still finish.";
    private const string StoppedReadMessage = "The script did not answer in time, so the app stopped it.";

    private readonly IJidokaProcess process;
    private readonly BdAdapter bd;
    private readonly JidokaHome home;
    private readonly TimeProvider clock;

    /// <param name="process">Starts a program.</param>
    /// <param name="bd">The adapter that learns of a write, because a script writes through bd.</param>
    /// <param name="home">The home that holds what jidoka keeps, as <see cref="JidokaHome"/> finds it.</param>
    /// <param name="clock">Times the wait on a script.</param>
    public JidokaAdapter(IJidokaProcess process, BdAdapter bd, JidokaHome home, TimeProvider clock)
    {
        this.process = process;
        this.bd = bd;
        this.home = home;
        this.clock = clock;
    }

    /// <summary>
    /// Writes one decision of the acceptance gate on an epic, by running the gate script in the
    /// project of the epic. The script refuses a decision that does not fit the epic and says why.
    /// </summary>
    public Task<JidokaWriteOutcome> DecideAsync(BeadAddress epic, GateDecision decision) =>
        WriteAsync(
            epic.Project,
            GateScript,
            [decision.Mode, epic.Id, .. decision.AfterTheEpic],
            decision.TakesTheFullSuite ? FullSuiteWaitLimit : WaitLimit);

    /// <summary>
    /// Reads the settings of an epic's factory rules that a person picks from a list, as the rules
    /// script lists them, together with the value that the epic holds for each.
    /// </summary>
    public Task<Read<IReadOnlyList<RuleSetting>>> RuleChoicesAsync(BeadAddress epic) =>
        ReadAsync(epic.Project, RulesScript, ["choices", epic.Id], ParsedChoices);

    /// <summary>
    /// Reads what the small decisions of the gate name, as the gate script lists it for an epic that
    /// waits there: the numbered assumptions, the tests that the cleanup removed and the beads found
    /// outside the epic. The script writes nothing for this read.
    /// </summary>
    public Task<Read<GateItems>> GateItemsAsync(BeadAddress epic) =>
        ReadAsync(epic.Project, GateScript, ["items", epic.Id], ParsedGateItems);

    /// <summary>
    /// Reads the factory state and the next step of every epic that the factory holds in a project, as
    /// the state script prints them. The script writes nothing for this read.
    /// </summary>
    public Task<Read<IReadOnlyList<EpicFactoryState>>> FactoryStatesAsync(ProjectPath project) =>
        ReadAsync(project, FactoryStateScript, ["--json"], ParsedFactoryStates);

    /// <summary>
    /// Stops the factory on an epic, by running the scheduler's stop in the project of the epic: it
    /// ends each open lap interrupted and the epic's waker, and records the stop in the heartbeat, so that a
    /// new manager takes the epic at once. It is how the person stops an epic whose host is gone.
    /// </summary>
    public Task<JidokaWriteOutcome> StopFactoryAsync(BeadAddress epic) =>
        WriteAsync(epic.Project, SchedulerScript, ["stop", epic.Id], WaitLimit);

    private async Task<Read<T>> ReadAsync<T>(
        ProjectPath project, string script, IReadOnlyList<string> arguments, Func<string, Read<T>> parse)
        where T : notnull
    {
        var ran = await RunAsync(project, script, arguments, WaitLimit, GivingUp.StopsTheScript);
        switch (ran)
        {
            case Ran.NotStarted notStarted:
                return new Read<T>.Unread(notStarted.Reason);
            case Ran.Abandoned:
                return new Read<T>.Unread(StoppedReadMessage);
            case Ran.Finished { Result.Succeeded: false } failed:
                return new Read<T>.Unread(Said(failed.Result));
            case Ran.Finished finished:
                return parse(finished.Result.StandardOutput);
            default:
                throw new InvalidOperationException("A run is one of three cases.");
        }
    }

    /// <summary>
    /// Changes settings of an epic's factory rules by running the rules script, which checks every
    /// setting before it writes any and posts one line on the epic for each change.
    /// </summary>
    public Task<JidokaWriteOutcome> SetRulesAsync(BeadAddress epic, IReadOnlyList<RuleChange> changes) =>
        WriteAsync(
            epic.Project,
            RulesScript,
            ["set", epic.Id, .. changes.Select(change => change.Argument)],
            WaitLimit);

    private async Task<JidokaWriteOutcome> WriteAsync(
        ProjectPath project, string script, IReadOnlyList<string> arguments, TimeSpan wait)
    {
        var ran = await RunAsync(project, script, arguments, wait, GivingUp.LeavesTheScriptRunning);
        switch (ran)
        {
            case Ran.NotStarted notStarted:
                return new JidokaWriteOutcome.Failed(notStarted.Reason);
            case Ran.Abandoned:
                return new JidokaWriteOutcome.Abandoned(AbandonedWriteMessage);
            case Ran.Finished { Result: var result }:
                if (JidokaExit.MayHaveWritten(result.ExitCode))
                {
                    bd.NameAWriteOf(project);
                }

                return result.Succeeded
                    ? new JidokaWriteOutcome.Written(result.StandardOutput.Trim())
                    : new JidokaWriteOutcome.Failed(Said(result));
            default:
                throw new InvalidOperationException("A run is one of three cases.");
        }
    }

    private async Task<Ran> RunAsync(
        ProjectPath project, string script, IReadOnlyList<string> arguments, TimeSpan wait, GivingUp givingUp)
    {
        var found = JidokaInstall.Find(home);
        if (found is not Read<JidokaInstall>.Given { Value: var install })
        {
            return new Ran.NotStarted(found is Read<JidokaInstall>.Unread { Reason: var reason } ? reason : string.Empty);
        }

        using var stop = new CancellationTokenSource();
        var run = process.RunAsync(
            install.Python,
            project.Value,
            [install.PathOf(script), .. arguments, $"--jidoka-home={home.Root}"],
            givingUp == GivingUp.StopsTheScript ? stop.Token : CancellationToken.None);
        var winner = await Task.WhenAny(run, Task.Delay(wait, clock));
        if (winner == run)
        {
            return new Ran.Finished(await run);
        }

        await stop.CancelAsync();
        return new Ran.Abandoned();
    }

    private static string Said(BdResult result)
    {
        var said = string.Join('\n', new[] { result.StandardError.Trim(), result.StandardOutput.Trim() }
            .Where(text => text.Length > 0));
        return said.Length > 0 ? said : $"The script stopped with exit code {result.ExitCode}.";
    }

    private static Read<IReadOnlyList<RuleSetting>> ParsedChoices(string printed)
    {
        try
        {
            using var document = JsonDocument.Parse(printed);
            var settings = new List<RuleSetting>();
            foreach (var setting in document.RootElement.GetProperty("settings").EnumerateArray())
            {
                var value = setting.GetProperty("value");
                settings.Add(new RuleSetting(
                    setting.GetProperty("name").GetString() ?? string.Empty,
                    [.. setting.GetProperty("choices").EnumerateArray().Select(RuleValue.Of)],
                    value.ValueKind == JsonValueKind.Null ? null : RuleValue.Of(value)));
            }

            return new Read<IReadOnlyList<RuleSetting>>.Given(settings);
        }
        catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException)
        {
            return new Read<IReadOnlyList<RuleSetting>>.Unread(
                "The rules script answered with something that is not a list of settings.");
        }
    }

    private static Read<GateItems> ParsedGateItems(string printed)
    {
        try
        {
            using var document = JsonDocument.Parse(printed);
            var root = document.RootElement;
            return new Read<GateItems>.Given(new GateItems(
                [.. root.GetProperty("assumptions").EnumerateArray().Select(each => new GateAssumption(
                    each.GetProperty("number").GetInt32(),
                    TextOf(each, "bead"),
                    TextOf(each, "title"),
                    TextOf(each, "text")))],
                [.. root.GetProperty("removed").EnumerateArray().Select(each => new RemovedTest(
                    TextOf(each, "test"),
                    TextOf(each, "file"),
                    TextOf(each, "covered_by")))],
                [.. root.GetProperty("outside").EnumerateArray().Select(each => new FoundOutsideTheEpic(
                    TextOf(each, "bead"),
                    TextOf(each, "title"),
                    TextOf(each, "found_in")))],
                [.. root.GetProperty("holdouts").EnumerateArray().Select(each => new GateHoldout(
                    each.GetProperty("number").GetInt32(),
                    TextOf(each, "app"),
                    TextOf(each, "scenario"),
                    each.GetProperty("promoted").GetBoolean()))]));
        }
        catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            return new Read<GateItems>.Unread("The gate script answered with something that is not the items of the gate.");
        }
    }

    private static Read<IReadOnlyList<EpicFactoryState>> ParsedFactoryStates(string printed)
    {
        try
        {
            using var document = JsonDocument.Parse(printed);
            var states = new List<EpicFactoryState>();
            foreach (var each in document.RootElement.GetProperty("epics").EnumerateArray())
            {
                var state = FactoryStates.Named(TextOf(each, "state"))
                    ?? throw new FormatException("The state script printed a state that it does not define.");
                var step = each.GetProperty("next_step");
                var command = step.GetProperty("command");
                states.Add(new EpicFactoryState(
                    TextOf(each, "epic"),
                    state,
                    new NextStep(
                        TextOf(step, "text"),
                        command.ValueKind == JsonValueKind.String ? command.GetString() : null),
                    [.. each.GetProperty("waiting_on").EnumerateArray().Select(waiting => TextOf(waiting, "bead"))]));
            }

            return new Read<IReadOnlyList<EpicFactoryState>>.Given(states);
        }
        catch (Exception exception) when (exception is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            return new Read<IReadOnlyList<EpicFactoryState>>.Unread(
                "The state script answered with something that is not the factory states.");
        }
    }

    private static string TextOf(JsonElement element, string name) => element.GetProperty(name).GetString() ?? string.Empty;

    /// <summary>
    /// What the app does with a script that outran its wait. A read is stopped, because a run left
    /// going keeps calling bd. A write is left to finish, because a script stopped midway could leave
    /// an epic half written.
    /// </summary>
    private enum GivingUp
    {
        StopsTheScript,
        LeavesTheScriptRunning,
    }

    private abstract record Ran
    {
        private Ran()
        {
        }

        public sealed record NotStarted(string Reason) : Ran;

        public sealed record Abandoned : Ran;

        public sealed record Finished(BdResult Result) : Ran;
    }
}
