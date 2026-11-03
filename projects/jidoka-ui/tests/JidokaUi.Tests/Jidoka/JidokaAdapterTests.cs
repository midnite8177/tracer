using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;

namespace JidokaUi.Tests.Jidoka;

/// <summary>
/// The jidoka adapter over a hand-written process, in temporary folders: the command line that each
/// gate decision and each rules call becomes, and what the adapter says of a script that refuses,
/// that is missing or that does not answer.
/// </summary>
public sealed class JidokaAdapterTests : IDisposable
{
    private readonly TempDirectory directory = new();
    private readonly FakeJidoka jidoka = new();
    private readonly FakeTimeProvider clock = new(new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
    private readonly List<ProjectPath> writtenProjects = [];
    private readonly JidokaAdapter adapter;
    private readonly BeadAddress epic;
    private readonly string home;

    public JidokaAdapterTests()
    {
        home = directory.CreateSubdirectory("jidoka-home");
        File.WriteAllText(Path.Combine(home, "settings.json"), """{"python": "/opt/python3"}""");
        Directory.CreateDirectory(Path.Combine(home, "plugins", "0.1.2", "jidoka", "scripts"));
        epic = new BeadAddress(ProjectPath.From(directory.CreateSubdirectory("project")), "b-1");
        var bd = new BdAdapter(new FakeBd(), clock);
        bd.Wrote += writtenProjects.Add;
        adapter = new JidokaAdapter(jidoka, bd, new JidokaHome(home), clock);
    }

    public void Dispose() => directory.Dispose();

    [Fact]
    public async Task RunsTheGateScriptWithTheModeAndTheEpicInTheProjectOfTheEpic()
    {
        jidoka.Prints("gate.py drop b-1", "b-1 is dropped and closed.");

        var outcome = await adapter.DecideAsync(epic, GateDecision.Drop());

        Assert.True(outcome.Wrote);
        Assert.Equal("b-1 is dropped and closed.", outcome.Output);
        Assert.Equal(["gate.py drop b-1"], jidoka.Invocations);
        Assert.Equal(["/opt/python3"], jidoka.Programs);
        Assert.Equal([epic.Project.Value], jidoka.Directories);
        Assert.Equal([home], jidoka.Homes);
    }

    [Fact]
    public async Task StopsTheFactoryOnAnEpicByRunningTheSchedulersStopInTheProjectOfTheEpic()
    {
        jidoka.Prints("scheduler.py stop b-1", """{"epic": "b-1", "interrupted": []}""");

        var outcome = await adapter.StopFactoryAsync(epic);

        Assert.True(outcome.Wrote);
        Assert.Equal(["scheduler.py stop b-1"], jidoka.Invocations);
        Assert.Equal([epic.Project.Value], jidoka.Directories);
        Assert.Equal(new[] { epic.Project }, writtenProjects);
    }

    [Fact]
    public async Task JoinsAMergeMessageToItsFlagSoThatAMessageLeadingWithADashStaysText()
    {
        jidoka.Prints("gate.py merge b-1 --message=-fix the site", "4f2a9c1");

        var outcome = await adapter.DecideAsync(epic, GateDecision.Merge("-fix the site"));

        Assert.True(outcome.Wrote);
        Assert.Equal("4f2a9c1", outcome.Output);
    }

    [Fact]
    public async Task AsksTheGateScriptForEachSmallDecisionWithItsOwnArguments()
    {
        jidoka
            .Prints("gate.py keep-finding b-1 b-9", string.Empty)
            .Prints("gate.py close-finding b-1 b-8", string.Empty)
            .Prints("gate.py wrong b-1 2 --why=It is a guess", string.Empty)
            .Prints("gate.py restore b-1 AddsTwo --file=MathTests.cs", string.Empty)
            .Prints("gate.py promote b-1 2", string.Empty);

        var outcomes = new[]
        {
            await adapter.DecideAsync(epic, GateDecision.KeepFinding("b-9")),
            await adapter.DecideAsync(epic, GateDecision.CloseFinding("b-8")),
            await adapter.DecideAsync(epic, GateDecision.Wrong(2, "It is a guess")),
            await adapter.DecideAsync(epic, GateDecision.Restore("AddsTwo", "MathTests.cs")),
            await adapter.DecideAsync(epic, GateDecision.Promote(2)),
        };

        Assert.All(outcomes, outcome => Assert.True(outcome.Wrote, outcome.Message));
    }

    [Fact]
    public async Task SaysWhatTheScriptSaidWhenItRefuses()
    {
        jidoka.Fails("gate.py drop b-1", "gate: b-1 does not wait at the gate");

        var outcome = await adapter.DecideAsync(epic, GateDecision.Drop());

        Assert.False(outcome.Wrote);
        Assert.False(outcome.GaveUp);
        Assert.Equal("gate: b-1 does not wait at the gate", outcome.Message);
    }

    [Fact]
    public async Task NamesTheFilesOfAMergeThatWaitsOnEditsFromItsOutputAsWellAsItsErrorStream()
    {
        jidoka.Exits("gate.py merge b-1 --message=Add", 3, "  src/a.cs", "gate: waiting on edits");

        var outcome = await adapter.DecideAsync(epic, GateDecision.Merge("Add"));

        Assert.Equal("gate: waiting on edits\nsrc/a.cs", outcome.Message);
    }

    [Fact]
    public async Task TellsTheBoardThatTheProjectChangedAfterAScriptRan()
    {
        jidoka.Prints("gate.py drop b-1", string.Empty);

        await adapter.DecideAsync(epic, GateDecision.Drop());

        Assert.Equal([epic.Project], writtenProjects);
    }

    [Fact]
    public async Task TellsTheBoardThatTheProjectChangedAfterAMergeThatStoppedHalfway()
    {
        jidoka.Exits("gate.py merge b-1 --message=Add", 4, "4f2a9c1", "gate: a closing step failed");

        var outcome = await adapter.DecideAsync(epic, GateDecision.Merge("Add"));

        Assert.False(outcome.Wrote);
        Assert.Equal([epic.Project], writtenProjects);
    }

    [Fact]
    public async Task TellsTheBoardNothingAfterAUsageError()
    {
        jidoka.Exits("gate.py drop b-1", 2, string.Empty, "usage: gate.py");

        await adapter.DecideAsync(epic, GateDecision.Drop());

        Assert.Empty(writtenProjects);
    }

    [Theory]
    [InlineData(JidokaExit.Refused)]
    [InlineData(JidokaExit.WaitingOnEdits)]
    public async Task TellsTheBoardNothingAfterAScriptThatRefusedOrWaitsOnEdits(int exitCode)
    {
        jidoka.Exits("gate.py merge b-1 --message=Add", exitCode, string.Empty, "gate: not now");

        await adapter.DecideAsync(epic, GateDecision.Merge("Add"));

        Assert.Empty(writtenProjects);
    }

    [Fact]
    public async Task TellsTheBoardThatTheProjectChangedAfterAMergeThatWentBackToTheGate()
    {
        jidoka.Exits("gate.py merge b-1 --message=Add", JidokaExit.BackAtTheGate, string.Empty, "gate: the suite failed");

        await adapter.DecideAsync(epic, GateDecision.Merge("Add"));

        Assert.Equal([epic.Project], writtenProjects);
    }

    [Fact]
    public async Task GivesUpOnAScriptThatOutrunsTheWaitLimitAndSaysItMayStillFinish()
    {
        jidoka.Holds("gate.py drop b-1");

        var deciding = adapter.DecideAsync(epic, GateDecision.Drop());
        clock.Advance(JidokaAdapter.WaitLimit);
        var outcome = await deciding;

        Assert.False(outcome.Wrote);
        Assert.True(outcome.GaveUp);
        Assert.Contains("may still finish", outcome.Message, StringComparison.Ordinal);
        Assert.False(jidoka.Stops.Single().IsCancellationRequested);
    }

    [Fact]
    public async Task StopsTheStateScriptWhenItOutrunsTheWaitLimitAndSaysItStoppedIt()
    {
        jidoka.Holds("factory_state.py --json");

        var reading = adapter.FactoryStatesAsync(epic.Project);
        Assert.False(jidoka.Stops.Single().IsCancellationRequested);
        clock.Advance(JidokaAdapter.WaitLimit);
        var read = await reading;

        Assert.True(jidoka.Stops.Single().IsCancellationRequested);
        var reason = Assert.IsType<Read<IReadOnlyList<EpicFactoryState>>.Unread>(read).Reason;
        Assert.Contains("stopped it", reason, StringComparison.Ordinal);
        Assert.DoesNotContain("may still finish", reason, StringComparison.Ordinal);
    }

    [Fact]
    public async Task WaitsLongerForAMergeBecauseItRunsTheFullSuite()
    {
        jidoka.Holds("gate.py merge b-1 --message=Add");

        var deciding = adapter.DecideAsync(epic, GateDecision.Merge("Add"));
        clock.Advance(JidokaAdapter.WaitLimit);
        Assert.False(deciding.IsCompleted);
        jidoka.Answers("gate.py merge b-1 --message=Add", "4f2a9c1");
        var outcome = await deciding;

        Assert.True(outcome.Wrote);
    }

    [Fact]
    public async Task StartsNoScriptAndSaysSoWhenJidokaHasNoSettings()
    {
        File.Delete(Path.Combine(home, "settings.json"));

        var outcome = await adapter.DecideAsync(epic, GateDecision.Drop());

        Assert.False(outcome.Wrote);
        Assert.Contains("name no Python", outcome.Message, StringComparison.Ordinal);
        Assert.Empty(jidoka.Invocations);
    }

    [Fact]
    public async Task StartsNoScriptAndSaysSoWhenJidokaHasNoSnapshotOfItsScripts()
    {
        Directory.Delete(Path.Combine(home, "plugins"), recursive: true);

        var outcome = await adapter.DecideAsync(epic, GateDecision.Drop());

        Assert.False(outcome.Wrote);
        Assert.Contains("no installed scripts", outcome.Message, StringComparison.Ordinal);
        Assert.Empty(jidoka.Invocations);
    }

    [Fact]
    public void FindsTheScriptsOfTheNewestSnapshotByVersionAndNotByName()
    {
        Directory.CreateDirectory(Path.Combine(home, "plugins", "0.1.10", "jidoka", "scripts"));
        Directory.CreateDirectory(Path.Combine(home, "plugins", "0.1.9", "jidoka", "scripts"));

        var install = Assert.IsType<Read<JidokaInstall>.Given>(JidokaInstall.Find(new JidokaHome(home))).Value;

        Assert.Equal(Path.Combine(home, "plugins", "0.1.10", "jidoka", "scripts"), install.Scripts);
        Assert.Equal("/opt/python3", install.Python);
    }

    [Fact]
    public async Task ListsTheSettingsThatTheRulesScriptOffersWithTheirChoicesAndTheValueTheEpicHolds()
    {
        jidoka.Prints("rules.py choices b-1", """
            {"epic": "b-1", "settings": [
              {"name": "lap_test_scope", "choices": ["targeted", "full"], "value": "full"},
              {"name": "lap_limit", "choices": [1, 2], "value": null},
              {"name": "discovered_bugs_into_epic", "choices": [true, false], "value": true}]}
            """);

        var read = await adapter.RuleChoicesAsync(epic);

        var settings = Assert.IsType<Read<IReadOnlyList<RuleSetting>>.Given>(read).Value;
        Assert.Equal(["lap_test_scope", "lap_limit", "discovered_bugs_into_epic"], settings.Select(setting => setting.Name));
        Assert.Equal(["targeted", "full"], settings[0].Choices.Select(choice => choice.Text));
        Assert.Equal("full", settings[0].Value?.Text);
        Assert.Equal(["1", "2"], settings[1].Choices.Select(choice => choice.Text));
        Assert.Null(settings[1].Value);
        Assert.True(settings[2].Holds(settings[2].Choices[0]));
    }

    [Fact]
    public async Task SaysWhyTheRulesScriptGaveNoSettingsWhenItRefusesTheEpic()
    {
        jidoka.Fails("rules.py choices b-1", "rules: b-1 is a task, not an epic");

        var read = await adapter.RuleChoicesAsync(epic);

        Assert.Equal("rules: b-1 is a task, not an epic", Assert.IsType<Read<IReadOnlyList<RuleSetting>>.Unread>(read).Reason);
    }

    [Fact]
    public async Task SaysThatTheRulesScriptAnsweredWithSomethingElseWhenItsOutputIsNotTheList()
    {
        jidoka.Prints("rules.py choices b-1", "not json");

        var read = await adapter.RuleChoicesAsync(epic);

        Assert.Contains("not a list of settings", Assert.IsType<Read<IReadOnlyList<RuleSetting>>.Unread>(read).Reason, StringComparison.Ordinal);
    }

    [Fact]
    public async Task SendsEachChangedSettingToTheRulesScriptAsANameAndItsJsonValue()
    {
        jidoka.Prints("rules.py set b-1 lap_limit=1 lap_test_scope=\"full\"", "{}");

        var outcome = await adapter.SetRulesAsync(
            epic,
            [
                new RuleChange("lap_limit", new RuleValue("1", "1")),
                new RuleChange("lap_test_scope", new RuleValue("\"full\"", "full")),
            ]);

        Assert.True(outcome.Wrote, outcome.Message);
        Assert.Equal([epic.Project], writtenProjects);
    }

    [Fact]
    public async Task ReadsTheNumberedAssumptionsTheRemovedTestsAndTheBeadsFoundOutsideFromTheGateScript()
    {
        jidoka.Prints("gate.py items b-1", """
            {"epic": "b-1",
             "assumptions": [{"number": 1, "bead": "b-1", "title": "The site", "text": "Dates are UTC"},
                             {"number": 2, "bead": "b-2", "title": "Add two", "text": "Rounds half up"}],
             "removed": [{"test": "AddsTwo", "file": "MathTests.cs", "covered_by": "AddsThree"}],
             "holdouts": [{"number": 1, "app": "shop", "scenario": "Pay 5.00 by card", "promoted": false},
                          {"number": 2, "app": "shop", "scenario": "Pay 5.00 in cash", "promoted": true}],
             "outside": [{"bead": "b-9", "title": "Split the module", "found_in": "b-2"}]}
            """);

        var read = await adapter.GateItemsAsync(epic);

        var items = Assert.IsType<Read<GateItems>.Given>(read).Value;
        Assert.Equal(
            [new GateHoldout(1, "shop", "Pay 5.00 by card", false), new GateHoldout(2, "shop", "Pay 5.00 in cash", true)],
            items.Holdouts);
        Assert.Equal([new GateAssumption(1, "b-1", "The site", "Dates are UTC"), new GateAssumption(2, "b-2", "Add two", "Rounds half up")], items.Assumptions);
        Assert.Equal([new RemovedTest("AddsTwo", "MathTests.cs", "AddsThree")], items.RemovedTests);
        Assert.Equal([new FoundOutsideTheEpic("b-9", "Split the module", "b-2")], items.FoundOutside);
        Assert.Equal(["gate.py items b-1"], jidoka.Invocations);
        Assert.Empty(writtenProjects);
    }

    [Fact]
    public async Task SaysWhyTheGateScriptGaveNoItemsWhenItRefusesTheEpic()
    {
        jidoka.Fails("gate.py items b-1", "gate: b-1 does not wait at the acceptance gate");

        var read = await adapter.GateItemsAsync(epic);

        Assert.Equal(
            "gate: b-1 does not wait at the acceptance gate",
            Assert.IsType<Read<GateItems>.Unread>(read).Reason);
    }

    [Fact]
    public async Task SaysThatTheGateScriptAnsweredWithSomethingElseWhenItsOutputIsNotTheItems()
    {
        jidoka.Prints("gate.py items b-1", "not json");

        var read = await adapter.GateItemsAsync(epic);

        Assert.Contains("not the items of the gate", Assert.IsType<Read<GateItems>.Unread>(read).Reason, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ReadsTheFactoryStateAndTheNextStepOfEachEpicFromTheStateScript()
    {
        jidoka.Prints(
            "factory_state.py --json",
            """
            {"epics": [
              {"epic": "b-1", "title": "The site", "state": "running", "heartbeat_age_seconds": 12, "watcher": false,
               "waiting_on": [],
               "next_step": {"action": "none", "text": "Nothing to do. The factory is running.", "command": null,
                             "run_after": null, "wakes_at": null, "wakes_on_answer": false}},
              {"epic": "b-2", "title": "The shop", "state": "waiting-on-you", "heartbeat_age_seconds": 40, "watcher": true,
               "waiting_on": [{"bead": "b-2.1", "kind": "question", "text": "Which plan?", "wakes": true}],
               "next_step": {"action": "answer", "text": "Answer: Which plan?. Answering wakes the factory by itself.",
                             "command": null, "run_after": null, "wakes_at": null, "wakes_on_answer": true}},
              {"epic": "b-3", "title": "The blog", "state": "stopped", "heartbeat_age_seconds": null, "watcher": false,
               "waiting_on": [],
               "next_step": {"action": "restart", "text": "Run /jidoka:factory to start the manager again.",
                             "command": "/jidoka:factory", "run_after": null, "wakes_at": null, "wakes_on_answer": false}}
            ]}
            """);

        var read = await adapter.FactoryStatesAsync(epic.Project);

        var states = Assert.IsType<Read<IReadOnlyList<EpicFactoryState>>.Given>(read).Value;
        Assert.Equal(
            [
                ("b-1", FactoryState.Running, new NextStep("Nothing to do. The factory is running.", null)),
                (
                    "b-2",
                    FactoryState.WaitingOnYou,
                    new NextStep("Answer: Which plan?. Answering wakes the factory by itself.", null)),
                (
                    "b-3",
                    FactoryState.Stopped,
                    new NextStep("Run /jidoka:factory to start the manager again.", "/jidoka:factory")),
            ],
            states.Select(state => (state.Epic, state.State, state.NextStep)));
        Assert.Empty(states[0].WaitingOn);
        Assert.Equal(["b-2.1"], states[1].WaitingOn);
        Assert.Empty(states[2].WaitingOn);
        Assert.Equal(["factory_state.py --json"], jidoka.Invocations);
        Assert.Equal([epic.Project.Value], jidoka.Directories);
        Assert.Empty(writtenProjects);
    }

    [Fact]
    public async Task ReadsAWaitingEpicFromTheStateScript()
    {
        jidoka.Prints(
            "factory_state.py --json",
            """
            {"epics": [{"epic": "b-1", "title": "The site", "state": "waiting", "heartbeat_age_seconds": 3, "watcher": true,
              "waiting_on": [],
              "next_step": {"action": "wait", "text": "Nothing to do. The factory wakes by itself.", "command": null,
                            "run_after": null, "wakes_at": 1700000000, "wakes_on_answer": false}}]}
            """);

        var read = await adapter.FactoryStatesAsync(epic.Project);

        var waiting = Assert.Single(Assert.IsType<Read<IReadOnlyList<EpicFactoryState>>.Given>(read).Value);
        Assert.Equal(
            ("b-1", FactoryState.Waiting, new NextStep("Nothing to do. The factory wakes by itself.", null)),
            (waiting.Epic, waiting.State, waiting.NextStep));
    }

    [Fact]
    public async Task SaysWhyTheStateScriptGaveNoStatesWhenItCouldNotReadTheBeads()
    {
        jidoka.Fails("factory_state.py --json", "factory_state: bd could not read the beads");

        var read = await adapter.FactoryStatesAsync(epic.Project);

        Assert.Equal(
            "factory_state: bd could not read the beads",
            Assert.IsType<Read<IReadOnlyList<EpicFactoryState>>.Unread>(read).Reason);
    }

    [Fact]
    public async Task SaysThatTheStateScriptAnsweredWithSomethingElseWhenItsOutputIsNotTheStates()
    {
        jidoka.Prints(
            "factory_state.py --json",
            """{"epics": [{"epic": "b-1", "title": "T", "state": "dancing", "next_step": {"text": "x", "command": null}}]}""");

        var read = await adapter.FactoryStatesAsync(epic.Project);

        Assert.Contains(
            "not the factory states",
            Assert.IsType<Read<IReadOnlyList<EpicFactoryState>>.Unread>(read).Reason,
            StringComparison.Ordinal);
    }

    [Fact]
    public async Task SaysWhyTheRulesScriptRefusedAValue()
    {
        jidoka.Fails(
            "rules.py set b-1 lap_limit=9",
            "rules: the factory rules of b-1 were not changed:\n  lap_limit must be below the repo's 3");

        var outcome = await adapter.SetRulesAsync(epic, [new RuleChange("lap_limit", new RuleValue("9", "9"))]);

        Assert.False(outcome.Wrote);
        Assert.Contains("lap_limit must be below the repo's 3", outcome.Message, StringComparison.Ordinal);
    }
}
