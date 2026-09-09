using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;

namespace TracerUi.Tests.Boards;

public sealed class BacklogReaderTests
{
    private static readonly ProjectPath Project = ProjectPath.From(Path.GetTempPath());

    private static BacklogReader ReaderOver(FakeBd bd) => new(new BdAdapter(bd, TimeProvider.System));

    private static FakeBd ABdThatPrints(string list, string ready, string blocked) =>
        new FakeBd()
            .Prints("list --all --limit 0 --json", list)
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
    public async Task ReportsTheProblemWhenBdCannotListTheBeads()
    {
        var bd = new FakeBd()
            .Fails("list --all --limit 0 --json", "unknown flag: --all")
            .Fails("list --json", "no beads database found in this directory");

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.False(outcome.Answered);
        Assert.Contains("no beads database found", outcome.Message);
    }

    [Fact]
    public async Task StillBuildsABacklogWhenBdCannotSayWhichBeadsAreReady()
    {
        var bd = new FakeBd()
            .Prints("list --all --limit 0 --json", """[{"id": "x-1", "title": "First", "status": "open"}]""")
            .Fails("ready --json", "unknown command \"ready\" for \"bd\"")
            .Fails("blocked --json", "unknown command \"blocked\" for \"bd\"");

        var outcome = await ReaderOver(bd).ReadAsync(Project);

        Assert.True(outcome.Answered);
        var row = Assert.Single(outcome.Backlog.ToBoard(BoardFilter.Everything).EveryRow);
        Assert.Equal("open", row.Status.Text);
    }
}
