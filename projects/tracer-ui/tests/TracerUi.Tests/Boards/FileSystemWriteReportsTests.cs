using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class FileSystemWriteReportsTests
{
    // The file system of macOS drops some writes unreported, and the first ones after a watch starts
    // most of all, so the test writes again at this interval until a report arrives.
    private static readonly TimeSpan BetweenWrites = TimeSpan.FromMilliseconds(100);

    private static readonly TimeSpan LongEnoughForTheFileSystem = TimeSpan.FromMinutes(1);

    [Fact]
    public async Task ReportsAWriteInTheDirectoryThatItWatches()
    {
        using var directory = new TempDirectory();
        var wrote = new TaskCompletionSource();

        using var watch = new FileSystemWriteReports().Start(directory.Path, () => wrote.TrySetResult(), () => { });

        using var giveUp = new CancellationTokenSource(LongEnoughForTheFileSystem);
        for (var write = 0; !wrote.Task.IsCompleted && !giveUp.IsCancellationRequested; write++)
        {
            await File.WriteAllTextAsync(Path.Combine(directory.Path, $"issues-{write}.jsonl"), "{}");
            await Task.WhenAny(wrote.Task, Task.Delay(BetweenWrites));
        }

        Assert.True(wrote.Task.IsCompletedSuccessfully);
    }
}
