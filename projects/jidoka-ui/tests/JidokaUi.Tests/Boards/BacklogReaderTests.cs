using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;

namespace JidokaUi.Tests.Boards;

public sealed class BacklogReaderTests
{
    private static readonly ProjectPath Project = ProjectPath.From(Path.GetTempPath());

    private const string ListCommand = "list --all --limit 0 --json";

    private static BacklogReader ReaderOver(FakeBd bd) => new(new BdAdapter(bd, TimeProvider.System));

    private static FakeBd ABdThatPrints(string list, string ready, string blocked) =>
        new FakeBd()
            .Prints(ListCommand, list)
            .Prints("ready --json", ready)
            .Prints("blocked --json", blocked);

    [Fact]
    public async Task BuildsABacklogFromTheListTheReadyBeadsAndTheBlockedBeads()
    {
        var bd = ABdThatPrints(
            """
            [
              {"id": "x", "title": "The epic", "issue_type": "epic", "status": "in_progress"},
              {"id": "x-1", "title": "First", "parent": "x", "status": "open", "priority": 1},
              {"id": "x-2", "title": "Second", "parent": "x", "status": "open", "priority": 2}
            ]
            """,
            """[{"id": "x-1"}]""",
            """[{"id": "x-2", "blocked_by": ["x-1"]}]""");

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.True(outcome.Answered);
        var board = outcome.Backlog.ToBoard(BoardFilter.Everything);
        Assert.Equal("The epic", board.Rows[0].Bead.Title);
        Assert.Equal(["ready", "blocked by First"], board.Rows.Skip(1).Select(row => row.Status.Text));
    }

    [Fact]
    public async Task WorksOutTheReadyBeadsFromTheListWhenNoOpenBeadWaitsOnAnother()
    {
        var bd = new FakeBd().Prints(
            ListCommand,
            """
            [
              {"id": "x", "title": "The epic", "issue_type": "epic", "status": "in_progress", "dependency_count": 0},
              {"id": "x-1", "title": "First", "parent": "x", "status": "open", "priority": 1, "dependency_count": 0},
              {"id": "x-2", "title": "Second", "parent": "x", "status": "deferred", "priority": 2, "dependency_count": 0},
              {"id": "x-3", "title": "Third", "parent": "x", "status": "closed", "priority": 2, "dependency_count": 2}
            ]
            """);

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.True(outcome.Answered);
        Assert.Equal([ListCommand], bd.Invocations);
        Assert.Contains("x-1", outcome.Backlog.ReadyIds);
        Assert.DoesNotContain("x-2", outcome.Backlog.ReadyIds);
        Assert.DoesNotContain("x-3", outcome.Backlog.ReadyIds);
        Assert.Empty(outcome.Backlog.Blockers);
        var statuses = outcome.Backlog.ToBoard(BoardFilter.Everything).EveryRow
            .ToDictionary(row => row.Bead.Id, row => row.Status.Kind);
        Assert.Equal(BeadStatusKind.Ready, statuses["x-1"]);
    }

    [Fact]
    public async Task ReadsTheReadyAndBlockedBeadsFromBdWhenAnOpenBeadWaitsOnAnother()
    {
        var bd = ABdThatPrints(
            """
            [
              {"id": "x-1", "title": "First", "status": "open", "dependency_count": 0},
              {"id": "x-2", "title": "Second", "status": "open", "dependency_count": 1}
            ]
            """,
            """[{"id": "x-1"}]""",
            """[{"id": "x-2", "blocked_by": ["x-1"]}]""");

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.Equal([ListCommand, "ready --json", "blocked --json"], bd.Invocations);
        Assert.Equal(["x-1"], outcome.Backlog.ReadyIds);
        Assert.Equal(["x-1"], outcome.Backlog.Blockers["x-2"]);
    }

    [Fact]
    public async Task ReadsTheReadyAndBlockedBeadsFromBdWhenTheListStatesNoCountOfWhatABeadWaitsOn()
    {
        var bd = ABdThatPrints(
            """[{"id": "x-1", "title": "First", "status": "open"}]""",
            """[{"id": "x-1"}]""",
            "[]");

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.Equal([ListCommand, "ready --json", "blocked --json"], bd.Invocations);
        Assert.Equal(["x-1"], outcome.Backlog.ReadyIds);
    }

    [Fact]
    public async Task ReadsTheReadyAndBlockedBeadsFromBdWhenAnOpenBeadCarriesADeferralDate()
    {
        var bd = ABdThatPrints(
            """
            [{"id": "x-1", "title": "First", "status": "open", "dependency_count": 0,
              "defer_until": "2999-01-01T00:00:00Z"}]
            """,
            "[]",
            "[]");

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.Equal([ListCommand, "ready --json", "blocked --json"], bd.Invocations);
        Assert.Empty(outcome.Backlog.ReadyIds);
    }

    [Fact]
    public async Task ReportsTheProblemWhenBdCannotListTheBeads()
    {
        var bd = new FakeBd()
            .Fails(ListCommand, "unknown flag: --all")
            .Fails("list --json", "no beads database found in this directory");

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.False(outcome.Answered);
        Assert.Contains("no beads database found", outcome.Message);
    }

    [Fact]
    public async Task StillBuildsABacklogWhenBdCannotSayWhichBeadsAreReady()
    {
        var bd = new FakeBd()
            .Prints(ListCommand, """[{"id": "x-1", "title": "First", "status": "open"}]""")
            .Fails("ready --json", "unknown command \"ready\" for \"bd\"")
            .Fails("blocked --json", "unknown command \"blocked\" for \"bd\"");

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.True(outcome.Answered);
        var row = Assert.Single(outcome.Backlog.ToBoard(BoardFilter.Everything).EveryRow);
        Assert.Equal("open", row.Status.Text);
    }
}
