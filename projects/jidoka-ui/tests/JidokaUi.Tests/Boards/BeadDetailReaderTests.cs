using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;

namespace JidokaUi.Tests.Boards;

public sealed class BeadDetailReaderTests
{
    private static readonly ProjectPath Project = ProjectPath.From(Path.GetTempPath());

    private const string Backlog = """
        [
          {"id": "x", "title": "The epic", "issue_type": "epic", "status": "in_progress"},
          {"id": "x-1", "title": "First", "parent": "x", "status": "open",
           "dependencies": [{"id": "x-9", "title": "Groundwork", "dependency_type": "blocks"}]},
          {"id": "x-2", "title": "The next slice", "status": "open",
           "dependencies": [{"id": "x-1", "title": "First", "dependency_type": "blocks"}]},
          {"id": "x-9", "title": "Groundwork", "status": "closed"}
        ]
        """;

    private static FakeBd ABdWithThatBacklog() =>
        new FakeBd()
            .Prints("list --all --limit 0 --json", Backlog)
            .Prints("ready --json", """[{"id": "x-1"}]""")
            .Prints("blocked --json", "[]");

    private static BeadDetailReader ReaderOf(FakeBd bd)
    {
        var adapter = new BdAdapter(bd, TimeProvider.System);
        return new BeadDetailReader(adapter, new BacklogReader(adapter));
    }

    [Fact]
    public async Task ReadsOneBeadWithItsEpicItsBlockersAndTheBeadsThatWaitForIt()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-1 --json", """
                [{"id": "x-1", "title": "First", "parent": "x", "status": "open",
                  "acceptance_criteria": "The page reads well.",
                  "dependencies": [{"id": "x-9", "title": "Groundwork", "dependency_type": "blocks"}]}]
                """)
            .Prints("comments x-1 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var detail = TheBeadOf(outcome);
        Assert.Equal("First", detail.Bead.Title);
        Assert.Equal("The page reads well.", detail.Bead.Prose.Acceptance);
        var facts = TheBacklogFactsOf(outcome);
        Assert.Equal("The epic", Assert.IsType<BeadLink>(facts.Epic).Title);
        Assert.Equal(["x-9"], facts.Blockers.Select(link => link.Id));
        Assert.Equal(["Groundwork"], facts.Blockers.Select(link => link.Title));
        Assert.Equal(["x-2"], facts.Dependents.Select(link => link.Id));
        Assert.Equal(["The next slice"], facts.Dependents.Select(link => link.Title));
        Assert.Equal("ready", detail.Status.Text);
    }

    private const string ATreeOfThreeLevels = """
        [
          {"id": "x", "title": "The epic", "issue_type": "epic", "status": "in_progress"},
          {"id": "x-0", "title": "Groundwork", "issue_type": "task", "parent": "x", "status": "closed"},
          {"id": "x-1", "title": "First", "issue_type": "task", "parent": "x", "status": "open"},
          {"id": "x-1-1", "title": "Deeper", "issue_type": "task", "parent": "x-1", "status": "open"}
        ]
        """;

    private static FakeBd ABdWithThatTree() =>
        new FakeBd()
            .Prints("list --all --limit 0 --json", ATreeOfThreeLevels)
            .Prints("ready --json", "[]")
            .Prints("blocked --json", "[]")
            .Prints("show x --json", """
                [{"id": "x", "title": "The epic", "issue_type": "epic", "status": "in_progress"}]
                """)
            .Prints("comments x --json", "[]");

    [Fact]
    public async Task ReadsTheBeadsThatThisOneHoldsDirectlyAndNoBeadFromADeeperLevel()
    {
        var outcome = await ReaderOf(ABdWithThatTree()).ReadAsync(Project, "x");

        Assert.Equal(["x-1", "x-0"], TheBacklogFactsOf(outcome).Held.Select(link => link.Id));
    }

    [Fact]
    public async Task PutsTheOpenBeadsThatOneBeadHoldsBeforeTheClosedOnes()
    {
        var outcome = await ReaderOf(ABdWithThatTree()).ReadAsync(Project, "x");

        Assert.Equal(
            [false, true],
            TheBacklogFactsOf(outcome).Held.Select(link => link.Status.IsClosed));
    }

    [Fact]
    public async Task GivesEachBeadThatItNamesTheResolvedStatusAndTheTypeThatARowOfItDraws()
    {
        var bd = ABdWithThatTree().Prints("ready --json", """[{"id": "x-1"}]""");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x");

        var held = TheBacklogFactsOf(outcome).Held[0];
        Assert.Equal("First", held.Title);
        Assert.Equal("task", held.Type);
        Assert.Equal("ready", held.Status.Text);
    }

    [Fact]
    public async Task ReadsEveryBeadOfTheBacklogBesideTheOneItShows()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-1 --json", """[{"id": "x-1", "title": "First"}]""")
            .Prints("comments x-1 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var given = Assert.IsType<BeadDetailRead.Given>(outcome);
        Assert.Equal(["x", "x-1", "x-2", "x-9"], given.Beads.Select(bead => bead.Id));
        Assert.Equal(["x"], given.Epics.Select(epic => epic.Id));
    }

    [Fact]
    public async Task RendersTheDescriptionOfTheBeadAsMarkdown()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-1 --json", """
                [{"id": "x-1", "title": "First", "description": "## Demo\n\nBrowse the board.\n"}]
                """)
            .Prints("comments x-1 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var detail = TheBeadOf(outcome);
        Assert.Contains("<h2", detail.Bead.Prose.DescriptionHtml);
        Assert.Contains("<p>Browse the board.</p>", detail.Bead.Prose.DescriptionHtml);
    }

    [Fact]
    public async Task ReadsTheCommentsOfTheBeadInTheOrderThatBdPrintsThem()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-1 --json", """[{"id": "x-1", "title": "First"}]""")
            .Prints("comments x-1 --json", """
                [{"author": "claude", "text": "First", "created_at": "2026-01-01T09:00:00Z"},
                 {"author": "sam", "text": "Second", "created_at": "2026-01-02T09:00:00Z"}]
                """);

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var detail = TheBeadOf(outcome);
        Assert.Equal(
            ["First", "Second"],
            TheCommentsOf(detail).Select(comment => comment.Text));
    }

    [Fact]
    public async Task ShowsTheCloseReasonOfAClosedBead()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-9 --json", """
                [{"id": "x-9", "title": "Groundwork", "status": "closed",
                  "close_reason": "a9eccef: the board shows the beads."}]
                """)
            .Prints("comments x-9 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-9");

        var detail = TheBeadOf(outcome);
        Assert.True(detail.Bead.HasCloseReason);
        Assert.Equal("a9eccef: the board shows the beads.", detail.Bead.CloseReason);
    }

    [Fact]
    public async Task ShowsTheNotesOfTheBead()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-1 --json", """
                [{"id": "x-1", "title": "First", "notes": "Read the log first."}]
                """)
            .Prints("comments x-1 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var detail = TheBeadOf(outcome);
        Assert.True(detail.Bead.Prose.HasNotes);
        Assert.Contains("Read the log first.", detail.Bead.Prose.NotesHtml);
    }

    [Fact]
    public async Task ReportsWhatBdWroteWhenItWillNotShowTheBead()
    {
        var bd = ABdWithThatBacklog().Fails("show x-9 --json", "issue not found: x-9");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-9");

        var failed = Assert.IsType<BeadDetailRead.Failed>(outcome);
        Assert.Contains("issue not found: x-9", failed.Reason);
    }

    [Fact]
    public async Task ReportsAGiveUpWhenBdDoesNotShowTheBeadInTime()
    {
        var bd = ABdWithThatBacklog().Holds("show x-1 --json");
        var clock = new FakeTimeProvider(new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
        var adapter = new BdAdapter(bd, clock);
        var reader = new BeadDetailReader(adapter, new BacklogReader(adapter));

        var reading = reader.ReadAsync(Project, "x-1");
        clock.Advance(BdAdapter.WaitLimit);
        var outcome = await reading;

        var abandoned = Assert.IsType<BeadDetailRead.Abandoned>(outcome);
        Assert.Contains("The app stopped it", abandoned.Reason, StringComparison.Ordinal);
        Assert.True(outcome.GaveUp);
    }

    [Fact]
    public async Task SaysThatTheProjectHasNoSuchBeadWhenBdShowsNone()
    {
        var bd = ABdWithThatBacklog().Prints("show x-7 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-7");

        var failed = Assert.IsType<BeadDetailRead.Failed>(outcome);
        Assert.Contains("x-7", failed.Reason);
    }

    [Fact]
    public async Task ShowsTheBeadAndSaysWhyWhenBdWillNotReadItsComments()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-1 --json", """[{"id": "x-1", "title": "First"}]""")
            .Fails("comments x-1 --json", "unknown command \"comments\" for \"bd\"");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var detail = TheBeadOf(outcome);
        Assert.Equal("First", detail.Bead.Title);
        var unread = Assert.IsType<Read<IReadOnlyList<BeadComment>>.Unread>(detail.Comments);
        Assert.Contains("unknown command", unread.Reason);
    }

    [Fact]
    public async Task TellsABeadThatCarriesNoCommentFromOneWhoseCommentsBdWouldNotGive()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-1 --json", """[{"id": "x-1", "title": "First"}]""")
            .Prints("comments x-1 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var detail = TheBeadOf(outcome);
        var given = Assert.IsType<Read<IReadOnlyList<BeadComment>>.Given>(detail.Comments);
        Assert.Empty(given.Value);
    }

    [Fact]
    public async Task ShowsTheBeadAndSaysWhyWhenBdWillNotListTheBacklog()
    {
        var bd = new FakeBd()
            .Fails("list --all --limit 0 --json", "unknown flag: --all")
            .Fails("list --json", "no beads database found in this directory")
            .Prints("show x-1 --json", """[{"id": "x-1", "title": "First", "parent": "x"}]""")
            .Prints("comments x-1 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var detail = TheBeadOf(outcome);
        Assert.Equal("First", detail.Bead.Title);
        var unread = Assert.IsType<Read<BacklogFacts>.Unread>(detail.BacklogFacts);
        Assert.Contains("no beads database found", unread.Reason);
    }

    [Fact]
    public async Task HoldsTheBacklogFactsWhenBdListsTheBacklog()
    {
        var bd = ABdWithThatBacklog()
            .Prints("show x-1 --json", """[{"id": "x-1", "title": "First"}]""")
            .Prints("comments x-1 --json", "[]");

        var outcome = await ReaderOf(bd).ReadAsync(Project, "x-1");

        var detail = TheBeadOf(outcome);
        Assert.IsType<Read<BacklogFacts>.Given>(detail.BacklogFacts);
    }

    private static BeadDetail TheBeadOf(BeadDetailRead outcome) =>
        Assert.IsType<BeadDetailRead.Given>(outcome).Detail;

    private static BacklogFacts TheBacklogFactsOf(BeadDetailRead outcome) =>
        Assert.IsType<Read<BacklogFacts>.Given>(TheBeadOf(outcome).BacklogFacts).Value;

    private static IReadOnlyList<BeadComment> TheCommentsOf(BeadDetail detail) =>
        Assert.IsType<Read<IReadOnlyList<BeadComment>>.Given>(detail.Comments).Value;
}
