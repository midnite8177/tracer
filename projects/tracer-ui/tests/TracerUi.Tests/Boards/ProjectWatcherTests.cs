using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Boards;

public sealed class ProjectWatcherTests
{
    // Far shorter than the timeout the test waits on, so a failure there means a lost report and
    // never a slow clock.
    private static readonly TimeSpan AShortQuietPeriod = TimeSpan.FromMilliseconds(20);

    // Longer than the burst of writes that the test makes, so that the burst coalesces.
    private static readonly TimeSpan AGenerousQuietPeriod = TimeSpan.FromMilliseconds(300);

    [Fact]
    public async Task InvalidatesTheBacklogWhenSomethingElseWritesInTheBeadsDirectory()
    {
        using var directory = new TempDirectory();
        var beads = directory.CreateSubdirectory(ProjectPathValidator.BeadsDirectoryName);
        var project = ProjectPath.From(directory.Path);
        var cache = ABacklogCache.OverASilentBd();
        var changed = new TaskCompletionSource<ProjectPath>();
        cache.Changed += path => changed.TrySetResult(path);

        using var watcher = new ProjectWatcher(project, cache, AShortQuietPeriod);
        await File.WriteAllTextAsync(Path.Combine(beads, "issues.jsonl"), "{}");

        var named = await changed.Task.WaitAsync(ABacklogCache.LongEnough);
        Assert.Equal(project, named);
    }

    [Fact]
    public async Task InvalidatesOnceWhenOneCommandOfBdWritesManyFiles()
    {
        using var directory = new TempDirectory();
        var beads = directory.CreateSubdirectory(ProjectPathValidator.BeadsDirectoryName);
        var project = ProjectPath.From(directory.Path);
        var cache = ABacklogCache.OverASilentBd();
        var count = 0;
        cache.Changed += _ => Interlocked.Increment(ref count);

        using var watcher = new ProjectWatcher(project, cache, AGenerousQuietPeriod);
        for (var file = 0; file < 5; file++)
        {
            await File.WriteAllTextAsync(Path.Combine(beads, $"part-{file}.jsonl"), "{}");
        }

        await Task.Delay(ABacklogCache.LongEnoughForAStrayInvalidationToLand(AGenerousQuietPeriod));
        Assert.Equal(1, Volatile.Read(ref count));
    }
}
