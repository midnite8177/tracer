using System.Collections.Concurrent;
using System.Diagnostics;
using System.Globalization;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Beads;

/// <summary>The one layer that owns every bd invocation.</summary>
public sealed class BdAdapter
{
    /// <summary>
    /// How long a caller waits for bd before the app gives up on a run. The abandoned read and the
    /// abandoned write follow from it, so it is part of the interface of the adapter, and the run
    /// gate reads it.
    /// </summary>
    public static readonly TimeSpan WaitLimit = TimeSpan.FromSeconds(30);

    private readonly BdRunGate gate;
    private readonly ConcurrentDictionary<ProjectPath, Lazy<Task<BdCapabilities>>> probed = new();
    private readonly Lock gathering = new();
    private readonly HashSet<ProjectPath> gathered = [];
    private int runs;

    public BdAdapter(IBdProcess process, TimeProvider clock)
    {
        gate = new BdRunGate(process, clock);
    }

    /// <summary>
    /// Names the project that a write of this app changed. The adapter is the one layer that makes
    /// a write, so a listener that follows this event misses none of them.
    /// </summary>
    public event Action<ProjectPath>? Wrote;

    /// <summary>
    /// Runs many writes and names each project that they changed once, at the end of the run. bd
    /// writes one bead at a time, and a listener that read a project between two of those writes
    /// would show a selection that is half written.
    /// </summary>
    public async Task<T> GatherTheWritesAsync<T>(Func<Task<T>> writes)
    {
        lock (gathering)
        {
            runs++;
        }

        try
        {
            return await writes();
        }
        finally
        {
            foreach (var project in EndOfARun())
            {
                Wrote?.Invoke(project);
            }
        }
    }

    private IReadOnlyList<ProjectPath> EndOfARun()
    {
        lock (gathering)
        {
            runs--;
            if (runs > 0)
            {
                return [];
            }

            var projects = gathered.ToArray();
            gathered.Clear();
            return projects;
        }
    }

    /// <summary>
    /// Names a project that a script of jidoka changed. The script writes through bd itself, so the
    /// adapter never saw the write, and a listener that follows <see cref="Wrote"/> still learns of it.
    /// </summary>
    public void NameAWriteOf(ProjectPath project) => NameTheProjectOrHoldItForTheRun(project);

    private void NameTheProjectOrHoldItForTheRun(ProjectPath project)
    {
        lock (gathering)
        {
            if (runs > 0)
            {
                gathered.Add(project);
                return;
            }
        }

        Wrote?.Invoke(project);
    }

    public Task<BdOutcome> ReadyAsync(ProjectPath project) =>
        OutcomeOfAsync(project.Value, ["ready", "--json"]);

    private static BdOutcome OutcomeOf(IReadOnlyList<string> arguments, BdResult result)
    {
        if (!result.Succeeded)
        {
            return new BdOutcome.Failed(BdFailure.Describe(arguments, result));
        }

        return BdJson.TryParse(result.StandardOutput, out var records)
            ? new BdOutcome.Given(records)
            : new BdOutcome.Failed(
                $"bd {string.Join(' ', arguments)} answered with something that is not JSON.");
    }

    private async Task<BdOutcome> OutcomeOfAsync(string workingDirectory, IReadOnlyList<string> arguments)
    {
        var run = await RunReadAsync(workingDirectory, arguments);
        return run.Match<BdOutcome>(
            result => OutcomeOf(arguments, result),
            reason => new BdOutcome.Abandoned(reason));
    }

    private const string AbandonedReadMessage =
        "bd has not answered. The app stopped it, so this read is no longer running.";

    private const string AbandonedWriteMessage =
        "bd has not answered. The app does not stop a write, so it may still have landed.";

    // One run of bd: it answered, or the app stopped waiting and says why.
    private abstract record Run
    {
        private Run()
        {
        }

        public T Match<T>(Func<BdResult, T> ran, Func<string, T> gaveUp) => this switch
        {
            Ran answered => ran(answered.Result),
            GaveUp stopped => gaveUp(stopped.Reason),
            _ => throw new UnreachableException(),
        };

        public sealed record Ran(BdResult Result) : Run;

        public sealed record GaveUp(string Reason) : Run;
    }

    private async Task<Run> RunReadAsync(string workingDirectory, IReadOnlyList<string> arguments) =>
        await gate.RunOrGiveUpAsync(workingDirectory, arguments, GivingUp.StopsTheProcess) is { } result
            ? new Run.Ran(result)
            : new Run.GaveUp(AbandonedReadMessage);

    private async Task<Run> RunWriteAsync(string workingDirectory, IReadOnlyList<string> arguments) =>
        await gate.RunOrGiveUpAsync(workingDirectory, arguments, GivingUp.LeavesTheProcessRunning) is { } result
            ? new Run.Ran(result)
            : new Run.GaveUp(AbandonedWriteMessage);

    // How a write that went through the capability check and the run ended. The write and the create
    // both end this way, and each turns the ending into its own outcome.
    private abstract record WriteEnd
    {
        private WriteEnd()
        {
        }

        public T Match<T>(Func<BdResult, T> wrote, Func<string, T> failed, Func<string, T> gaveUp) => this switch
        {
            Wrote written => wrote(written.Result),
            Failed refused => failed(refused.Reason),
            GaveUp stopped => gaveUp(stopped.Reason),
            _ => throw new UnreachableException(),
        };

        public sealed record Wrote(BdResult Result) : WriteEnd;

        public sealed record Failed(string Reason) : WriteEnd;

        public sealed record GaveUp(string Reason) : WriteEnd;
    }

    /// <summary>
    /// Reads every bead of the project, whatever its status. bd list hides the closed beads and
    /// applies a limit by default, so the read asks for every status and lifts the limit. An older
    /// bd has no --all flag, and answers the plain list instead.
    /// </summary>
    public async Task<BdOutcome> ListAsync(ProjectPath project)
    {
        string[] everyStatus = ["list", "--all", "--limit", "0", "--json"];
        var run = await RunReadAsync(project.Value, everyStatus);
        if (run is Run.GaveUp gaveUp)
        {
            return new BdOutcome.Abandoned(gaveUp.Reason);
        }

        if (run is Run.Ran { Result.Succeeded: true } ran)
        {
            return OutcomeOf(everyStatus, ran.Result);
        }

        return await OutcomeOfAsync(project.Value, ["list", "--json"]);
    }

    /// <summary>Reads one bead in full, with the dependency edges that name the beads it depends on.</summary>
    public Task<BdOutcome> ShowAsync(BeadAddress bead) =>
        OutcomeOfAsync(bead.Project.Value, ["show", bead.Id, "--json"]);

    /// <summary>Reads the comments of one bead, in the order that bd prints them.</summary>
    public Task<BdOutcome> CommentsAsync(BeadAddress bead) =>
        OutcomeOfAsync(bead.Project.Value, ["comments", bead.Id, "--json"]);

    /// <summary>Reads the beads that bd calls blocked, each with the beads that block it.</summary>
    public Task<BdOutcome> BlockedAsync(ProjectPath project) =>
        OutcomeOfAsync(project.Value, ["blocked", "--json"]);

    /// <summary>
    /// Adds one comment to a bead. A comment appends, where a write of the notes or the description
    /// replaces what was there, so it loses nothing that another writer left.
    /// </summary>
    public Task<BdWriteOutcome> CommentAsync(BeadAddress bead, string text) =>
        WriteAsync(bead, UiVerbs.AddAComment, ["comment", bead.Id, text]);

    public Task<BdWriteOutcome> AddLabelAsync(BeadAddress bead, BeadLabel label) =>
        WriteAsync(bead, UiVerbs.LabelABead, ["label", "add", bead.Id, label.Word]);

    public Task<BdWriteOutcome> RemoveLabelAsync(BeadAddress bead, BeadLabel label) =>
        WriteAsync(bead, UiVerbs.LabelABead, ["label", "remove", bead.Id, label.Word]);

    /// <summary>
    /// Adds and removes labels of a bead in one update. It names only the labels that change and
    /// never the whole set, so a label that another writer put on the bead meanwhile stays. The
    /// adapter refuses a change that names no label and runs nothing. bd splits the value of
    /// --add-label and --remove-label at each comma, so a label with a comma lands as two labels.
    /// </summary>
    public Task<BdWriteOutcome> ChangeLabelsAsync(
        BeadAddress bead,
        IReadOnlyList<BeadLabel> adds,
        IReadOnlyList<BeadLabel> removes)
    {
        if (adds.Count == 0 && removes.Count == 0)
        {
            return BdWriteOutcome.FailedTask("A change of the labels needs a label to add or to take off.");
        }

        return WriteAsync(
            bead,
            UiVerbs.ChangeTheLabels,
            [
                "update",
                bead.Id,
                .. adds.SelectMany(label => new[] { "--add-label", label.Word }),
                .. removes.SelectMany(label => new[] { "--remove-label", label.Word }),
            ]);
    }

    /// <summary>Sets the priority of a bead. bd takes a number from 0 to 4, where 0 is the most urgent.</summary>
    public Task<BdWriteOutcome> SetPriorityAsync(BeadAddress bead, long priority) =>
        WriteAsync(
            bead,
            UiVerbs.SetThePriority,
            ["update", bead.Id, "--priority", priority.ToString(CultureInfo.InvariantCulture)]);

    public Task<BdWriteOutcome> SetTypeAsync(BeadAddress bead, BeadTypeWord type) =>
        WriteAsync(bead, UiVerbs.SetTheType, ["update", bead.Id, "--type", type.Word()]);

    /// <summary>Moves a bead into an epic.</summary>
    public Task<BdWriteOutcome> SetParentAsync(BeadAddress bead, string epicId) =>
        WriteAsync(bead, UiVerbs.MoveIntoAnEpic, ["update", bead.Id, "--parent", epicId]);

    /// <summary>
    /// Sets the title and the description of a bead in one write. A bead with no title is
    /// unreadable on the board, so the adapter refuses an empty title and runs nothing.
    /// </summary>
    public Task<BdWriteOutcome> EditProseAsync(BeadAddress bead, string title, string description)
    {
        var newTitle = title.Trim();
        return newTitle.Length == 0
            ? BdWriteOutcome.FailedTask("A bead needs a title.")
            : WriteAsync(
                bead,
                UiVerbs.EditTheProse,
                ["update", bead.Id, "--title", newTitle, "--description", description]);
    }

    /// <summary>
    /// Sets the acceptance criteria of a bead. bd takes them on their own, so this write sends no
    /// other part of the prose and leaves the title, the description and the notes as they were.
    /// </summary>
    public Task<BdWriteOutcome> EditAcceptanceAsync(BeadAddress bead, string acceptance) =>
        WriteAsync(
            bead,
            UiVerbs.EditTheAcceptanceCriteria,
            ["update", bead.Id, "--acceptance", acceptance]);

    /// <summary>
    /// Replaces the notes of a bead with the text that the person wrote. bd keeps no earlier copy of
    /// them, so the UI asks for this write on its own and never folds it into another one.
    /// </summary>
    public Task<BdWriteOutcome> RewriteNotesAsync(BeadAddress bead, string notes) =>
        WriteAsync(bead, UiVerbs.RewriteTheNotes, ["update", bead.Id, "--notes", notes]);

    /// <summary>Adds a blocker to a bead, so that the blocker must close before the bead is ready.</summary>
    public Task<BdWriteOutcome> AddBlockerAsync(BeadAddress bead, string blockerId) =>
        EdgeAsync(bead, blockerId, "add");

    public Task<BdWriteOutcome> RemoveBlockerAsync(BeadAddress bead, string blockerId) =>
        EdgeAsync(bead, blockerId, "remove");

    // Adds or removes one dependency edge. bd names the bead first and its blocker second, so the
    // two subcommands take the same pair in the same order.
    private Task<BdWriteOutcome> EdgeAsync(BeadAddress bead, string blockerId, string subcommand)
    {
        var blocker = blockerId.Trim();
        if (blocker.Length == 0)
        {
            return BdWriteOutcome.FailedTask("An edge needs the blocker at its far end.");
        }

        return string.Equals(blocker, bead.Id, StringComparison.Ordinal)
            ? BdWriteOutcome.FailedTask("A bead cannot block itself.")
            : WriteAsync(bead, UiVerbs.EditADependencyEdge, ["dep", subcommand, bead.Id, blocker]);
    }

    public Task<BdWriteOutcome> SetStatusAsync(BeadAddress bead, StoredStatusWord status) =>
        WriteAsync(bead, UiVerbs.SetTheStatus, ["update", bead.Id, "--status", status.Word()]);

    /// <summary>
    /// Closes a bead with the reason that the person gave. A close without a reason leaves a hole in
    /// the history of the bead, so the adapter refuses it and runs nothing.
    /// </summary>
    public Task<BdWriteOutcome> CloseAsync(BeadAddress bead, string reason) =>
        reason.Trim().Length == 0
            ? BdWriteOutcome.FailedTask(
                "A close needs a reason. The history of this bead is what a later reader has.")
            : WriteAsync(bead, UiVerbs.CloseWithAReason, ["close", bead.Id, "--reason", reason]);

    /// <summary>
    /// Creates a bead from a title, a type and the epic that is to hold it. A null epic leaves the
    /// bead unparented. The create asks bd for the id alone, because the app names the new bead in
    /// the writes that follow.
    /// </summary>
    public async Task<BdCreateOutcome> CreateAsync(
        ProjectPath project,
        string title,
        string type,
        string? epicId)
    {
        var named = title.Trim();
        if (named.Length == 0)
        {
            return new BdCreateOutcome.Failed("A bead needs a title.");
        }

        var verb = epicId is null ? UiVerbs.CreateABead : UiVerbs.CreateInAnEpic;
        string[] arguments = epicId is null
            ? ["create", "--title", named, "--type", type, "--silent"]
            : ["create", "--title", named, "--type", type, "--parent", epicId, "--silent"];
        return await MakeAsync(project, verb, arguments);
    }

    /// <summary>
    /// Creates an epic from a title alone, and sets it to in progress at once. An epic that stayed
    /// open would read as ready work, and an epic is a container and never work of its own.
    /// </summary>
    public async Task<BdCreateOutcome> CreateEpicAsync(ProjectPath project, string title)
    {
        var named = title.Trim();
        if (named.Length == 0)
        {
            return new BdCreateOutcome.Failed("An epic needs a title.");
        }

        string[] arguments = ["create", "--title", named, "--type", "epic", "--silent"];
        var made = await MakeAsync(project, UiVerbs.CreateAnEpic, arguments);
        if (made is not BdCreateOutcome.Made epic)
        {
            return made;
        }

        var started = await SetStatusAsync(new BeadAddress(project, epic.BeadId), StoredStatusWord.InProgress);
        return started.Wrote
            ? made
            : new BdCreateOutcome.MadeButNotStarted(
                epic.BeadId,
                $"bd made the epic {epic.BeadId}, but it is still open. {started.Message}");
    }

    private async Task<BdCreateOutcome> MakeAsync(
        ProjectPath project,
        UiVerb verb,
        IReadOnlyList<string> arguments)
    {
        var end = await EndOfAWriteAsync(project, verb, arguments);
        return end.Match<BdCreateOutcome>(
            result => result.StandardOutput.Trim() is { Length: > 0 } id
                ? new BdCreateOutcome.Made(id)
                : new BdCreateOutcome.Failed("bd made a bead but printed no id for it."),
            reason => new BdCreateOutcome.Failed(reason),
            reason => new BdCreateOutcome.Abandoned(reason));
    }

    /// <summary>
    /// Defers a bead without naming a date. bd takes one on --until, and this write sends none, so
    /// a person who wants a date runs bd itself.
    /// </summary>
    public Task<BdWriteOutcome> DeferAsync(BeadAddress bead) =>
        WriteAsync(bead, UiVerbs.DeferABead, ["defer", bead.Id]);

    private async Task<BdWriteOutcome> WriteAsync(
        BeadAddress bead,
        UiVerb verb,
        IReadOnlyList<string> arguments)
    {
        var end = await EndOfAWriteAsync(bead.Project, verb, arguments);
        return end.Match<BdWriteOutcome>(
            _ => new BdWriteOutcome.Written(),
            reason => new BdWriteOutcome.Failed(reason),
            reason => new BdWriteOutcome.Abandoned(reason));
    }

    // Asks the capabilities, refuses a verb that this bd lacks, runs the write, and names the project
    // when bd made the change.
    private async Task<WriteEnd> EndOfAWriteAsync(
        ProjectPath project,
        UiVerb verb,
        IReadOnlyList<string> arguments)
    {
        var capabilities = await CapabilitiesAsync(project);
        var missing = capabilities.MissingCapability(verb);
        if (missing.Length > 0)
        {
            return new WriteEnd.Failed(missing);
        }

        var run = await RunWriteAsync(project.Value, arguments);
        var end = run.Match<WriteEnd>(
            result => result.Succeeded
                ? new WriteEnd.Wrote(result)
                : new WriteEnd.Failed(BdFailure.Describe(arguments, result)),
            reason => new WriteEnd.GaveUp(reason));
        if (end is WriteEnd.Wrote)
        {
            NameTheProjectOrHoldItForTheRun(project);
        }

        return end;
    }

    /// <summary>Probes the installed bd for this project. The answer holds for the life of the app.</summary>
    public Task<BdCapabilities> CapabilitiesAsync(ProjectPath project) =>
        // The Lazy is what holds the probe to one run. GetOrAdd may run its factory on more than one
        // thread and keep only the first answer, so without it two callers that arrive together each
        // launch a whole probe, which is a bd process per command the probe asks about.
        probed.GetOrAdd(project, path => new Lazy<Task<BdCapabilities>>(() => ProbeAsync(path))).Value;

    private async Task<BdCapabilities> ProbeAsync(ProjectPath project)
    {
        var version = await ProbeRunAsync(project, ["version"]);
        var help = await ProbeRunAsync(project, ["--help"]);

        var commandHelp = new Dictionary<string, BdResult>(StringComparer.Ordinal);
        foreach (var command in UiVerbs.Commands)
        {
            commandHelp[command] = await ProbeRunAsync(project, [command, "--help"]);
        }

        var beads = await SampleAsync(project);
        var comments = await CommentsOfOneBeadAsync(project, beads);
        return CapabilityProbe.From(version, help, commandHelp, beads, comments);
    }

    private async Task<BdResult> ProbeRunAsync(ProjectPath project, IReadOnlyList<string> arguments) =>
        (await RunReadAsync(project.Value, arguments)).Match(result => result, _ => GaveUpOnTheProbe);

    private static readonly BdResult GaveUpOnTheProbe = new(-1, string.Empty, AbandonedReadMessage);

    private async Task<BdComments> CommentsOfOneBeadAsync(
        ProjectPath project,
        IReadOnlyList<BeadRecord> sample)
    {
        var identifier = IdOfTheBeadWithTheMostComments(sample);
        if (identifier.Length == 0)
        {
            return BdComments.Unread("This project has no bead, so the probe read no comment.");
        }

        var outcome = await CommentsAsync(new BeadAddress(project, identifier));
        if (!outcome.Answered)
        {
            return BdComments.Unread(outcome.Message);
        }

        if (outcome.Records.Count == 0)
        {
            return BdComments.Unread($"Bead {identifier} has no comment, so the probe read no name.");
        }

        return new BdComments(BeadFields.ResolveCommentsFrom(outcome.Records), string.Empty);
    }

    // Reads a sample of beads for the probe. bd omits a field from its JSON when no bead in the
    // sample sets it, so the probe reads every bead of the project.
    private async Task<IReadOnlyList<BeadRecord>> SampleAsync(ProjectPath project) =>
        (await ListAsync(project)).Records;

    private static string IdOfTheBeadWithTheMostComments(IReadOnlyList<BeadRecord> sample) =>
        sample
            .Where(bead => bead.Text(BeadFields.IdNames).Length > 0)
            .OrderByDescending(bead => bead.Number(BeadFields.CommentCountNames, 0))
            .Select(bead => bead.Text(BeadFields.IdNames))
            .FirstOrDefault(string.Empty);
}
