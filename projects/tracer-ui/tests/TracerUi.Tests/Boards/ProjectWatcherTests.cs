using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Boards;

public sealed class ProjectWatcherTests
{
    // Far shorter than the timeout the test waits on, so a failure there means the watcher never
    // invalidated, and never a slow clock.
    private static readonly TimeSpan AShortQuietPeriod = TimeSpan.FromMilliseconds(20);

    private static readonly TimeSpan AQuietPeriodLongerThanTheBurst = TimeSpan.FromMilliseconds(300);

    private static readonly ProjectPath Project = ProjectPath.From(Path.Combine(Path.GetTempPath(), "a-project"));

    [Fact]
    public async Task InvalidatesTheBacklogWhenSomethingElseWritesInTheBeadsDirectory()
    {
        var reports = new FakeWriteReports();
        var cache = ABacklogCache.OverASilentBd();
        var changed = new TaskCompletionSource<BacklogChange>();
        cache.Changed += change => changed.TrySetResult(change);

        using var watcher = new ProjectWatcher(Project, cache, AShortQuietPeriod, reports);
        reports.ReportWrite(Project.BeadsDirectory);

        var named = await changed.Task.WaitAsync(Signals.LongEnough);
        Assert.Equal(Project, named.Project);
        Assert.Equal(BacklogChangeKind.Watch, named.Kind);
    }

    [Fact]
    public async Task InvalidatesOnceWhenOneCommandOfBdWritesManyFiles()
    {
        var reports = new FakeWriteReports();
        var cache = ABacklogCache.OverASilentBd();
        var count = 0;
        cache.Changed += _ => Interlocked.Increment(ref count);

        using var watcher = new ProjectWatcher(Project, cache, AQuietPeriodLongerThanTheBurst, reports);
        for (var file = 0; file < 5; file++)
        {
            reports.ReportWrite(Project.BeadsDirectory);
        }

        await Task.Delay(ABacklogCache.LongEnoughForAStrayInvalidationToLand(AQuietPeriodLongerThanTheBurst));
        Assert.Equal(1, Volatile.Read(ref count));
    }

    [Fact]
    public async Task InvalidatesTheBacklogWhenTheFileSystemDropsTheReportsOfWrites()
    {
        var reports = new FakeWriteReports();
        var cache = ABacklogCache.OverASilentBd();
        var changed = new TaskCompletionSource<BacklogChange>();
        cache.Changed += change => changed.TrySetResult(change);

        using var watcher = new ProjectWatcher(Project, cache, AShortQuietPeriod, reports);
        reports.LoseReports(Project.BeadsDirectory);

        var named = await changed.Task.WaitAsync(Signals.LongEnough);
        Assert.Equal(Project, named.Project);
        Assert.Equal(BacklogChangeKind.Watch, named.Kind);
    }
}
