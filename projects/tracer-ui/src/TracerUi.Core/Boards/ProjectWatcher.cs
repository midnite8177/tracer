using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The watch on the .beads directory of one project. An agent writes to .beads while the app is
/// open, so a change there invalidates the backlog of that project and the board reads it again.
/// </summary>
/// <remarks>
/// One command of bd writes several files, and the file system reports each write on its own. The
/// watch therefore waits for a quiet period after the last report before it invalidates, so one
/// command of bd costs one read of the backlog. The file system also drops the reports it cannot
/// hold, and it says so once; the watch starts again after that, because a watch that stopped
/// leaves a stale board with nothing to say why.
/// </remarks>
public sealed class ProjectWatcher : IDisposable
{
    private readonly ProjectPath project;
    private readonly BacklogCache cache;
    private readonly TimeSpan quietPeriod;
    private readonly FileSystemWatcher watcher;
    private readonly Timer quiet;

    public ProjectWatcher(ProjectPath project, BacklogCache cache, TimeSpan quietPeriod)
    {
        this.project = project;
        this.cache = cache;
        this.quietPeriod = quietPeriod;
        quiet = new Timer(_ => this.cache.Invalidate(this.project));
        watcher = new FileSystemWatcher(project.BeadsDirectory)
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

    private void OnChange(object sender, FileSystemEventArgs report) => StartTheQuietPeriodAgain();

    // Starts the watch again after the file system dropped the reports that it could not hold, and
    // invalidates the backlog, which is stale by an unknown amount then. A directory that a person
    // deleted takes the watch with it, and the board of that project reads bd only on demand.
    private void OnLostReports(object sender, ErrorEventArgs lost)
    {
        StartTheWatchAgainOrLetItGo();
        StartTheQuietPeriodAgain();
    }

    // Lets the restart go when the directory is gone, which the file system reports as an
    // IOException or an ArgumentException, and when this watcher is disposed, which it reports as an
    // ObjectDisposedException. Neither leaves anything to do. The failure stays here because this
    // runs on the thread that reported the error, where a throw meets no catch and ends the app.
    private void StartTheWatchAgainOrLetItGo()
    {
        try
        {
            watcher.EnableRaisingEvents = false;
            watcher.EnableRaisingEvents = true;
        }
        catch (Exception restarting)
            when (restarting is IOException or ArgumentException or ObjectDisposedException)
        {
        }
    }

    private void StartTheQuietPeriodAgain() => quiet.Change(quietPeriod, Timeout.InfiniteTimeSpan);

    public void Dispose()
    {
        watcher.EnableRaisingEvents = false;
        watcher.Dispose();
        quiet.Dispose();
    }
}
