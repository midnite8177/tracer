using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

/// <summary>
/// Reports of writes that a test raises on demand, so that a test of a project watcher waits on no
/// file system. A report reaches every watch that runs on the directory it names, and no other, on
/// the caller's thread before the call returns.
/// </summary>
public sealed class FakeWriteReports : IWriteReports
{
    private readonly List<Watch> running = [];

    public IDisposable Start(string directory, Action wrote, Action lostReports)
    {
        var watch = new Watch(this, directory, wrote, lostReports);
        lock (running)
        {
            running.Add(watch);
        }

        return watch;
    }

    public void ReportWrite(string directory)
    {
        foreach (var watch in RunningOn(directory))
        {
            watch.Wrote();
        }
    }

    public void LoseReports(string directory)
    {
        foreach (var watch in RunningOn(directory))
        {
            watch.LostReports();
        }
    }

    private List<Watch> RunningOn(string directory)
    {
        lock (running)
        {
            return running
                .Where(watch => string.Equals(watch.Directory, directory, StringComparison.Ordinal))
                .ToList();
        }
    }

    private void Stop(Watch watch)
    {
        lock (running)
        {
            running.Remove(watch);
        }
    }

    private sealed class Watch(FakeWriteReports reports, string directory, Action wrote, Action lostReports)
        : IDisposable
    {
        public string Directory { get; } = directory;

        public void Wrote() => wrote();

        public void LostReports() => lostReports();

        public void Dispose() => reports.Stop(this);
    }
}
