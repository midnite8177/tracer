using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Boards;

public sealed class ProjectWatchersTests
{
    [Fact]
    public async Task WatchesAProjectThatItAlreadyWatchesOnlyOnce()
    {
        using var directory = new TempDirectory();
        var beads = directory.CreateSubdirectory(ProjectPathValidator.BeadsDirectoryName);
        var project = ProjectPath.From(directory.Path);
        var cache = ABacklogCache.OverASilentBd();
        var count = 0;
        var changed = new TaskCompletionSource();
        cache.Changed += _ =>
        {
            Interlocked.Increment(ref count);
            changed.TrySetResult();
        };

        using var watchers = new ProjectWatchers(cache);
        watchers.Watch(project);
        watchers.Watch(project);
        await File.WriteAllTextAsync(Path.Combine(beads, "issues.jsonl"), "{}");

        await changed.Task.WaitAsync(ABacklogCache.LongEnough);
        await Task.Delay(ABacklogCache.LongEnoughForAStrayInvalidationToLand(ProjectWatchers.QuietPeriod));
        Assert.Equal(1, Volatile.Read(ref count));
    }

    [Fact]
    public async Task InvalidatesNothingForAProjectThatHasNoBeadsDirectory()
    {
        using var directory = new TempDirectory();
        var project = ProjectPath.From(directory.Path);
        var cache = ABacklogCache.OverASilentBd();
        var count = 0;
        cache.Changed += _ => Interlocked.Increment(ref count);

        using var watchers = new ProjectWatchers(cache);
        watchers.Watch(project);
        await File.WriteAllTextAsync(Path.Combine(directory.Path, "issues.jsonl"), "{}");

        await Task.Delay(ABacklogCache.LongEnoughForAStrayInvalidationToLand(ProjectWatchers.QuietPeriod));
        Assert.Equal(0, Volatile.Read(ref count));
    }
}
