namespace TracerUi.Core.Boards;

/// <summary>
/// The reports of writes that a <see cref="FileSystemWatcher"/> makes. After the file system drops
/// reports, the watch starts again and goes on reporting.
/// </summary>
public sealed class FileSystemWriteReports : IWriteReports
{
    public IDisposable Start(string directory, Action wrote, Action lostReports) =>
        new Watch(directory, wrote, lostReports);

    private sealed class Watch : IDisposable
    {
        private readonly FileSystemWatcher watcher;
        private readonly Action wrote;
        private readonly Action lostReports;

        public Watch(string directory, Action wrote, Action lostReports)
        {
            this.wrote = wrote;
            this.lostReports = lostReports;
            watcher = new FileSystemWatcher(directory)
            {
                IncludeSubdirectories = true,
                NotifyFilter = NotifyFilters.FileName
                    | NotifyFilters.DirectoryName
                    | NotifyFilters.LastWrite
                    | NotifyFilters.Size,
            };

            watcher.Changed += OnChange;
            watcher.Created += OnChange;
            watcher.Deleted += OnChange;
            watcher.Renamed += OnChange;
            watcher.Error += OnLostReports;
            watcher.EnableRaisingEvents = true;
        }

        private void OnChange(object sender, FileSystemEventArgs report) => wrote();

        private void OnLostReports(object sender, ErrorEventArgs lost)
        {
            StartTheWatchAgainOrLetItGo();
            lostReports();
        }

        // Lets the restart go when the directory is gone, which the file system reports as an
        // IOException or an ArgumentException, and when this watch is disposed, which it reports as
        // an ObjectDisposedException. Neither leaves anything to do, because the board of a project
        // whose directory is gone still reads bd on demand. The failure stays here because
        // this runs on the thread that reported the error, where a throw meets no catch and ends the
        // app.
        private void StartTheWatchAgainOrLetItGo()
        {
            try
            {
                // A watcher that reported an error can stop raising events. Without the restart the
                // board goes stale, with nothing to say why.
                watcher.EnableRaisingEvents = false;
                watcher.EnableRaisingEvents = true;
            }
            catch (Exception restarting)
                when (restarting is IOException or ArgumentException or ObjectDisposedException)
            {
            }
        }

        public void Dispose()
        {
            watcher.EnableRaisingEvents = false;
            watcher.Dispose();
        }
    }
}
