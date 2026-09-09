using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;

namespace TracerUi.Tests.Boards;

public sealed class BacklogCacheTests
{
    private const string ListCommand = "list --all --limit 0 --json";

    private static readonly ProjectPath First = ProjectPath.From(Path.Combine(Path.GetTempPath(), "first"));
    private static readonly ProjectPath Second = ProjectPath.From(Path.Combine(Path.GetTempPath(), "second"));

    private static FakeBd ABdThatLists() =>
        new FakeBd()
            .Prints(ListCommand, """[{"id": "x-1", "title": "First", "status": "open"}]""")
            .Prints("ready --json", "[]")
            .Prints("blocked --json", "[]");

    private static BacklogCache CacheOver(FakeBd bd)
    {
        var adapter = new BdAdapter(bd, TimeProvider.System);
        return new BacklogCache(new BacklogReader(adapter), adapter);
    }

    [Fact]
    public async Task AsksBdOnceAndHoldsTheAnswerForTheNextRead()
    {
        var bd = ABdThatLists();
        var cache = CacheOver(bd);

        var first = await cache.ReadAsync(First);
        var again = await cache.ReadAsync(First);

        Assert.True(again.Answered);
        Assert.Same(first, again);
        Assert.Equal(1, bd.Runs(First.Value, ListCommand));
    }

    [Fact]
    public async Task AsksBdAgainAfterAnInvalidationOfThatProject()
    {
        var bd = ABdThatLists();
        var cache = CacheOver(bd);
        await cache.ReadAsync(First);

        cache.Invalidate(First);
        var again = await cache.ReadAsync(First);

        Assert.True(again.Answered);
        Assert.Equal(2, bd.Runs(First.Value, ListCommand));
    }

    [Fact]
    public async Task LeavesTheOtherProjectsHeldWhenOneProjectIsInvalidated()
    {
        var bd = ABdThatLists();
        var cache = CacheOver(bd);
        await cache.ReadAsync(First);
        await cache.ReadAsync(Second);

        cache.Invalidate(First);
        await cache.ReadAsync(First);
        await cache.ReadAsync(Second);

        Assert.Equal(2, bd.Runs(First.Value, ListCommand));
        Assert.Equal(1, bd.Runs(Second.Value, ListCommand));
    }

    [Fact]
    public void NamesTheProjectThatChangedWhenItDropsABacklog()
    {
        var cache = CacheOver(ABdThatLists());
        var named = new List<ProjectPath>();
        cache.Changed += change => named.Add(change.Project);

        cache.Invalidate(Second);

        Assert.Equal([Second], named);
    }

    [Fact]
    public void RaisesAWriteChangeWhenAWriteOfThisAppInvalidatesTheProject()
    {
        var cache = CacheOver(ABdThatLists());
        BacklogChange? change = null;
        cache.Changed += raised => change = raised;

        cache.Invalidate(Second);

        Assert.Equal(BacklogChangeKind.Write, change?.Kind);
    }

    [Fact]
    public void RaisesAWatchChangeWhenTheProjectWatcherInvalidatesTheProject()
    {
        var cache = CacheOver(ABdThatLists());
        BacklogChange? change = null;
        cache.Changed += raised => change = raised;

        cache.InvalidateFromWatch(Second);

        Assert.Equal(BacklogChangeKind.Watch, change?.Kind);
    }

    [Fact]
    public async Task AsksBdAgainAfterTheProjectWatcherInvalidatesTheProject()
    {
        var bd = ABdThatLists();
        var cache = CacheOver(bd);
        await cache.ReadAsync(First);

        cache.InvalidateFromWatch(First);
        var again = await cache.ReadAsync(First);

        Assert.True(again.Answered);
        Assert.Equal(2, bd.Runs(First.Value, ListCommand));
    }

    [Fact]
    public async Task DoesNotHoldAnAnswerThatBdFailedToGive()
    {
        var bd = new FakeBd()
            .Fails(ListCommand, "database is locked")
            .Fails("list --json", "database is locked");
        var cache = CacheOver(bd);

        var first = await cache.ReadAsync(First);
        var again = await cache.ReadAsync(First);

        Assert.False(first.Answered);
        Assert.False(again.Answered);
        Assert.Equal(2, bd.Runs(First.Value, ListCommand));
    }

    [Fact]
    public async Task DropsTheBacklogOfTheProjectThatTheAppItselfWroteTo()
    {
        var bd = ABdThatLists()
            .Prints("version", "bd version 1.2.2")
            .Prints("--help", """
                Working With Issues:
                  comment           Add a comment to an issue
                """)
            .Prints("comment --help", "Flags:")
            .Prints("comment x-1 I read this today", string.Empty);
        var adapter = new BdAdapter(bd, TimeProvider.System);
        var cache = new BacklogCache(new BacklogReader(adapter), adapter);
        await cache.ReadAsync(First);
        BacklogChange? change = null;
        cache.Changed += raised => change = raised;

        await adapter.CommentAsync(new BeadAddress(First, "x-1"), "I read this today");
        await cache.ReadAsync(First);

        Assert.Equal(2, bd.Runs(First.Value, "ready --json"));
        Assert.Equal(BacklogChangeKind.Write, change?.Kind);
    }
}
