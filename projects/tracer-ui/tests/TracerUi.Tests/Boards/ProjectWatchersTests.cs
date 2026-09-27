using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Boards;

public sealed class ProjectWatchersTests
{
    [Fact]
    public async Task WatchesAProjectThatItAlreadyWatchesOnlyOnce()
    {
        using var directory = new TempDirectory();
        directory.CreateSubdirectory(ProjectPathValidator.BeadsDirectoryName);
        var project = ProjectPath.From(directory.Path);
        var reports = new FakeWriteReports();
        var cache = ABacklogCache.OverASilentBd();
        var count = 0;
        var changed = new TaskCompletionSource();
        cache.Changed += _ =>
        {
            Interlocked.Increment(ref count);
            changed.TrySetResult();
        };

        using var watchers = new ProjectWatchers(cache, reports);
        watchers.Watch(project);
        watchers.Watch(project);
        reports.ReportWrite(project.BeadsDirectory);

        await changed.Task.WaitAsync(Signals.LongEnough);
        await Task.Delay(ABacklogCache.LongEnoughForAStrayInvalidationToLand(ProjectWatchers.QuietPeriod));
        Assert.Equal(1, Volatile.Read(ref count));
    }

    [Fact]
    public async Task InvalidatesNothingForAProjectThatHasNoBeadsDirectory()
    {
        using var directory = new TempDirectory();
        var project = ProjectPath.From(directory.Path);
        var reports = new FakeWriteReports();
        var cache = ABacklogCache.OverASilentBd();
        var count = 0;
        cache.Changed += _ => Interlocked.Increment(ref count);

        using var watchers = new ProjectWatchers(cache, reports);
        watchers.Watch(project);
        reports.ReportWrite(project.BeadsDirectory);

        await Task.Delay(ABacklogCache.LongEnoughForAStrayInvalidationToLand(ProjectWatchers.QuietPeriod));
        Assert.Equal(0, Volatile.Read(ref count));
    }
}
