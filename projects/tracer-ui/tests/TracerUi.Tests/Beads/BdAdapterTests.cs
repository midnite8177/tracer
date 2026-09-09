using TracerUi.Core.Beads;
using TracerUi.Core.Projects;
using TracerUi.Tests;

namespace TracerUi.Tests.Beads;

public class BdAdapterTests
{
    private static readonly ProjectPath Project = ProjectPath.From(Path.GetTempPath());

    [Fact]
    public async Task ReadsTheBeadsThatBdReadyPrintsAsAJsonArray()
    {
        var bd = new FakeBd().Prints("ready --json", """[{"id": "x-1", "title": "First"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ReadyAsync(Project);

        Assert.True(outcome.Answered);
        Assert.Equal(["id", "title"], outcome.Records.Single().FieldNames.Order(StringComparer.Ordinal));
    }

    [Fact]
    public async Task ReadsTheBeadsThatAnOlderBdPrintsAsOneJsonObjectPerLine()
    {
        var bd = new FakeBd().Prints(
            "ready --json",
            """
            {"id": "x-1", "type": "task"}
            {"id": "x-2", "type": "bug"}
            """);
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ReadyAsync(Project);

        Assert.True(outcome.Answered);
        Assert.Equal(2, outcome.Records.Count);
    }

    [Fact]
    public async Task ReadsTheBeadsThatABdVersionWrapsInAnObject()
    {
        var bd = new FakeBd().Prints("ready --json", """{"issues": [{"id": "x-1"}]}""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ReadyAsync(Project);

        Assert.True(outcome.Answered);
        Assert.Single(outcome.Records);
    }

    [Fact]
    public async Task ReportsWhatBdWroteOnStandardErrorWhenTheReadFails()
    {
        var bd = new FakeBd().Fails("ready --json", "no beads database found in this directory");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ReadyAsync(Project);

        Assert.False(outcome.Answered);
        Assert.Contains("no beads database found", outcome.Message);
        Assert.Empty(outcome.Records);
    }

    [Fact]
    public async Task ReportsTheExitCodeWhenTheReadFailsAndBdWritesNothing()
    {
        var bd = new FakeBd().Fails("ready --json", string.Empty);
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ReadyAsync(Project);

        Assert.False(outcome.Answered);
        Assert.Contains("bd ready", outcome.Message);
        Assert.Contains("1", outcome.Message);
    }

    [Fact]
    public async Task ReportsTheVersionNumberOfTheInstalledBd()
    {
        var bd = new FakeBd().Prints("version", "bd version 1.2.2 (Homebrew)");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal("1.2.2", capabilities.Version);
    }

    [Fact]
    public async Task ReportsTheWholeVersionLineWhenItHoldsNoVersionNumber()
    {
        var bd = new FakeBd().Prints("version", "bd (built from source)");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal("bd (built from source)", capabilities.Version);
    }

    [Fact]
    public async Task ReportsTheProblemWhenTheAppCannotRunBdAtAll()
    {
        var bd = new FakeBd();
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal(string.Empty, capabilities.Version);
        Assert.Contains("bd version", capabilities.Problem);
    }

    [Fact]
    public async Task ReadsTheVerbsOutOfTheHelpThatBdPrints()
    {
        var bd = new FakeBd()
            .Prints("version", "bd version 1.2.2")
            .Prints("--help", """
                Usage:
                  bd [command]

                Working With Issues:
                  close             Close one or more issues
                  create            Create a new issue
                  update            Update one or more issues

                Additional Commands:
                  defer             Defer one or more issues for later

                Flags:
                      --json                      Output in JSON format
                  -h, --help                      help for bd
                """);
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal(["close", "create", "defer", "update"], capabilities.Verbs.Order());
    }

    [Fact]
    public async Task ResolvesAUiVerbThroughTheCommandAndTheFlagsThatBdOffers()
    {
        var adapter = new BdAdapter(BdWithUpdate(), TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.True(capabilities.Supports(MoveIntoAnEpic));
        Assert.Equal(string.Empty, capabilities.MissingCapability(MoveIntoAnEpic));
    }

    [Fact]
    public async Task NamesTheCommandThatTheInstalledBdDoesNotHave()
    {
        var adapter = new BdAdapter(BdWithUpdate(), TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.False(capabilities.Supports(DeferABead));
        Assert.Equal("bd has no defer command.", capabilities.MissingCapability(DeferABead));
    }

    [Fact]
    public async Task NamesTheFlagThatTheCommandOfTheInstalledBdDoesNotHave()
    {
        var adapter = new BdAdapter(BdWithUpdate(), TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.False(capabilities.Supports(SetTheDueDate));
        Assert.Equal("bd update has no --due flag.", capabilities.MissingCapability(SetTheDueDate));
    }

    private static readonly UiVerb MoveIntoAnEpic = new("Move a bead into an epic", "update", [], ["--parent"]);

    private static readonly UiVerb DeferABead = new("Defer a bead", "defer", [], []);

    private static readonly UiVerb SetTheDueDate = new("Set the due date", "update", [], ["--due"]);

    private static FakeBd BdWithUpdate() =>
        new FakeBd()
            .Prints("version", "bd version 1.2.2")
            .Prints("--help", """
                Working With Issues:
                  update            Update one or more issues
                """)
            .Prints("update --help", """
                Update one or more issues

                Flags:
                      --parent string     Set the parent epic
                  -p, --priority int      Set the priority
                """);

    [Fact]
    public async Task ReportsTheJsonFieldNamesThatThisVersionOfBdEmits()
    {
        var bd = BdWithUpdate().Prints(
            "list --json",
            """[{"id": "x-1", "issue_type": "task", "owner": "sam", "acceptance_criteria": "done"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal("issue_type", capabilities.Fields["type"]);
        Assert.Equal("owner", capabilities.Fields["assignee"]);
        Assert.Equal("acceptance_criteria", capabilities.Fields["acceptance"]);
    }

    [Fact]
    public async Task ReportsTheOtherNamesThatAnOlderVersionOfBdEmitsForTheSameFields()
    {
        var bd = BdWithUpdate().Prints(
            "list --json",
            """[{"id": "x-1", "type": "task", "assignee": "sam", "acceptance": "done"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal("type", capabilities.Fields["type"]);
        Assert.Equal("assignee", capabilities.Fields["assignee"]);
        Assert.Equal("acceptance", capabilities.Fields["acceptance"]);
    }

    [Fact]
    public async Task LeavesAFieldUnresolvedWhenNoBeadShowsIt()
    {
        var bd = BdWithUpdate().Prints("list --json", """[{"id": "x-1"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal("id", capabilities.Fields["id"]);
        Assert.Equal(string.Empty, capabilities.Fields["notes"]);
    }

    [Fact]
    public async Task ProbesOneProjectOnceAndAnswersLaterQuestionsFromTheCache()
    {
        var bd = BdWithUpdate();
        var adapter = new BdAdapter(bd, TimeProvider.System);

        await adapter.CapabilitiesAsync(Project);
        var runsAfterTheProbe = bd.Invocations.Count;
        await adapter.CapabilitiesAsync(Project);

        Assert.Equal(runsAfterTheProbe, bd.Invocations.Count);
    }

    [Fact]
    public async Task ProbesEachProjectOnItsOwn()
    {
        var bd = BdWithUpdate();
        var adapter = new BdAdapter(bd, TimeProvider.System);

        await adapter.CapabilitiesAsync(Project);
        var runsAfterTheProbe = bd.Invocations.Count;
        await adapter.CapabilitiesAsync(ProjectPath.From(Path.Combine(Path.GetTempPath(), "other-repository")));

        Assert.Equal(runsAfterTheProbe * 2, bd.Invocations.Count);
    }

    [Fact]
    public async Task SaysThatItCouldNotAskWhenTheProbeDidNotRun()
    {
        var adapter = new BdAdapter(new FakeBd(), TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.False(capabilities.VerbsKnown);
        Assert.False(capabilities.Supports(DeferABead));
        Assert.Contains("could not ask", capabilities.MissingCapability(DeferABead));
    }

    [Fact]
    public async Task SaysThatItCouldNotAskWhenTheHelpOfBdDoesNotAnswer()
    {
        var bd = new FakeBd().Prints("version", "bd version 1.2.2");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal("1.2.2", capabilities.Version);
        Assert.False(capabilities.VerbsKnown);
        Assert.Contains("could not ask", capabilities.MissingCapability(DeferABead));
    }

    [Fact]
    public async Task FailsTheReadWhenBdExitsWellButPrintsSomethingThatIsNotJson()
    {
        var bd = new FakeBd().Prints("ready --json", "Segmentation fault");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ReadyAsync(Project);

        Assert.False(outcome.Answered);
        Assert.Contains("bd ready --json", outcome.Message);
    }

    [Fact]
    public async Task ReadsNoBeadsAndStillAnswersWhenBdPrintsNothing()
    {
        var bd = new FakeBd().Prints("ready --json", string.Empty);
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ReadyAsync(Project);

        Assert.True(outcome.Answered);
        Assert.Empty(outcome.Records);
    }

    [Fact]
    public async Task CountsAFlagOnlyWhereTheHelpDeclaresItAndNotWhereTheProseNamesIt()
    {
        var bd = new FakeBd()
            .Prints("version", "bd version 1.2.2")
            .Prints("--help", """
                Working With Issues:
                  update            Update one or more issues
                """)
            .Prints("update --help", """
                Update one or more issues. Pass --parent to move the bead into an epic.

                Flags:
                  -p, --priority int      Set the priority
                """);
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.True(capabilities.Supports(SetThePriority));
        Assert.False(capabilities.Supports(MoveIntoAnEpic));
    }

    private static readonly UiVerb SetThePriority = new("Set the priority", "update", [], ["--priority"]);

    [Fact]
    public async Task SamplesEveryStatusSoThatAFieldOnlyAClosedBeadSetsStillResolves()
    {
        var bd = BdWithUpdate().Prints(
            "list --all --limit 0 --json",
            """[{"id": "x-1", "labels": ["ui"], "close_reason": "shipped"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal("labels", capabilities.Fields["labels"]);
        Assert.Equal("close_reason", capabilities.Fields["close-reason"]);
    }

    [Fact]
    public async Task ReadsTheCommentFieldNamesFromTheCommandThatHoldsTheComments()
    {
        var bd = BdWithUpdate()
            .Prints("list --all --limit 0 --json", """[{"id": "x-1"}]""")
            .Prints(
                "comments x-1 --json",
                """[{"id": "c-1", "issue_id": "x-1", "author": "sam", "text": "Looks good", "created_at": "2026-01-01T00:00:00Z"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.True(capabilities.Comments.Answered);
        Assert.Equal("text", capabilities.Comments.Fields["text"]);
        Assert.Equal("author", capabilities.Comments.Fields["author"]);
        Assert.Equal("created_at", capabilities.Comments.Fields["created"]);
    }

    [Fact]
    public async Task ReadsThePlainListWhenThisBdHasNoFlagForEveryStatus()
    {
        var bd = BdWithUpdate().Prints("list --json", """[{"id": "x-1", "issue_type": "task"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Equal("issue_type", capabilities.Fields["type"]);
    }

    [Fact]
    public async Task ProbesTheCommentsOfABeadThatHasSomeAndNotOfTheFirstBead()
    {
        var bd = BdWithUpdate()
            .Prints(
                "list --all --limit 0 --json",
                """[{"id": "x-1", "comment_count": 0}, {"id": "x-2", "comment_count": 3}]""")
            .Prints(
                "comments x-2 --json",
                """[{"author": "sam", "text": "Looks good", "created_at": "2026-01-01T00:00:00Z"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.True(capabilities.Comments.Answered);
        Assert.Equal("text", capabilities.Comments.Fields["text"]);
    }

    [Fact]
    public async Task SaysWhyItLearnedNoCommentNameWhenBdWillNotPrintTheComments()
    {
        var bd = BdWithUpdate()
            .Prints("list --all --limit 0 --json", """[{"id": "x-1"}]""")
            .Fails("comments x-1 --json", "unknown command \"comments\" for \"bd\"");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.False(capabilities.Comments.Answered);
        Assert.Contains("bd comments x-1 --json", capabilities.Comments.Problem);
        Assert.Equal(string.Empty, capabilities.Comments.Fields["text"]);
    }

    [Fact]
    public async Task ReportsWhetherThisBdCanReadTheCommentsOfABead()
    {
        var bd = new FakeBd()
            .Prints("version", "bd version 1.2.2")
            .Prints("--help", """
                Working With Issues:
                  comments          View or manage comments on an issue
                """)
            .Prints("comments --help", """
                View or manage comments on an issue

                Flags:
                      --json      Output in JSON format
                """);
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var capabilities = await adapter.CapabilitiesAsync(Project);

        Assert.Contains(UiVerbs.All, verb => verb.Command == "comments");
        Assert.True(capabilities.Supports(UiVerbs.All.Single(verb => verb.Command == "comments")));
    }

    [Fact]
    public async Task ReadsEveryBeadOfTheProjectWhateverItsStatus()
    {
        var bd = new FakeBd().Prints(
            "list --all --limit 0 --json",
            """[{"id": "x-1", "status": "closed"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ListAsync(Project);

        Assert.True(outcome.Answered);
        Assert.Single(outcome.Records);
    }

    [Fact]
    public async Task FallsBackToThePlainListWhenTheInstalledBdHasNoAllFlag()
    {
        var bd = new FakeBd()
            .Fails("list --all --limit 0 --json", "unknown flag: --all")
            .Prints("list --json", """[{"id": "x-1"}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ListAsync(Project);

        Assert.True(outcome.Answered);
        Assert.Single(outcome.Records);
    }

    [Fact]
    public async Task ReportsWhatBdWroteWhenNeitherListWorks()
    {
        var bd = new FakeBd()
            .Fails("list --all --limit 0 --json", "unknown flag: --all")
            .Fails("list --json", "no beads database found in this directory");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ListAsync(Project);

        Assert.False(outcome.Answered);
        Assert.Contains("no beads database found", outcome.Message);
    }

    [Fact]
    public async Task ReadsTheBeadsThatBlockEachBlockedBead()
    {
        var bd = new FakeBd().Prints(
            "blocked --json",
            """[{"id": "x-1", "blocked_by": ["x-2", "x-3"]}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.BlockedAsync(Project);

        Assert.True(outcome.Answered);
        Assert.Equal(["x-2", "x-3"], outcome.Records.Single().Strings(BeadFields.BlockedByNames));
    }

    [Fact]
    public async Task ReadsTheOneBeadThatBdShowPrints()
    {
        var bd = new FakeBd().Prints(
            "show x-1 --json",
            """[{"id": "x-1", "title": "First", "notes": "Read the log first."}]""");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ShowAsync(new BeadAddress(Project, "x-1"));

        Assert.True(outcome.Answered);
        Assert.Equal("First", outcome.Records.Single().Text(BeadFields.Candidates("title")));
    }

    [Fact]
    public async Task ReportsWhatBdWroteWhenItKnowsNoBeadWithThatId()
    {
        var bd = new FakeBd().Fails("show x-9 --json", "issue not found: x-9");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.ShowAsync(new BeadAddress(Project, "x-9"));

        Assert.False(outcome.Answered);
        Assert.Contains("issue not found: x-9", outcome.Message);
    }

    [Fact]
    public async Task ReadsTheCommentsOfOneBeadInTheOrderThatBdPrintsThem()
    {
        var bd = new FakeBd().Prints(
            "comments x-1 --json",
            """
            [{"author": "sam", "text": "First", "created_at": "2026-01-01T09:00:00Z"},
             {"author": "claude", "text": "Second", "created_at": "2026-01-02T09:00:00Z"}]
            """);
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.CommentsAsync(new BeadAddress(Project, "x-1"));

        Assert.True(outcome.Answered);
        Assert.Equal(
            ["First", "Second"],
            outcome.Records.Select(record => record.Text(BeadFields.TextOfAComment)));
    }

    [Fact]
    public async Task GivesUpOnAReadThatOutrunsTheWaitLimitWithoutClaimingToHaveStoppedBd()
    {
        var bd = new FakeBd().Holds("ready --json");
        var clock = new FakeTimeProvider(Start);
        var adapter = new BdAdapter(bd, clock);

        var reading = adapter.ReadyAsync(Project);
        clock.Advance(BdAdapter.WaitLimit);
        var outcome = await reading;

        Assert.False(outcome.Answered);
        Assert.True(outcome.GaveUp);
        Assert.DoesNotContain("stopped", outcome.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GivesUpOnAWriteThatOutrunsTheWaitLimitAndSaysItMayStillLand()
    {
        var bd = BdWithUpdate().Holds("update x-1 --priority 1");
        var clock = new FakeTimeProvider(Start);
        var adapter = new BdAdapter(bd, clock);

        var writing = adapter.SetPriorityAsync(new BeadAddress(Project, "x-1"), 1);
        clock.Advance(BdAdapter.WaitLimit);
        var outcome = await writing;

        Assert.False(outcome.Wrote);
        Assert.True(outcome.GaveUp);
        Assert.Contains("may still have landed", outcome.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task GivesUpOnTheProbeThatOutrunsTheWaitLimitAndReportsWhatItCouldNotAsk()
    {
        var bd = new FakeBd().Holds("version");
        var clock = new FakeTimeProvider(Start);
        var adapter = new BdAdapter(bd, clock);

        var probing = adapter.CapabilitiesAsync(Project);
        clock.Advance(BdAdapter.WaitLimit);
        var capabilities = await probing;

        Assert.Equal(string.Empty, capabilities.Version);
        Assert.False(capabilities.VerbsKnown);
        Assert.Contains("bd version", capabilities.Problem, StringComparison.Ordinal);
        Assert.DoesNotContain("stopped", capabilities.Problem, StringComparison.Ordinal);
    }

    private static readonly DateTimeOffset Start = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
}
