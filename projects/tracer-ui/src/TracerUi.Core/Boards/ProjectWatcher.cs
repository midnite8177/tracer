using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The watch on the .beads directory of one project. An agent writes to .beads while the app is
/// open, so a change there invalidates the backlog of that project.
/// </summary>
/// <remarks>
/// One command of bd writes several files, and the file system reports each write on its own. The
/// watch therefore waits for a quiet period after the last report before it invalidates, so one
/// command of bd costs one read of the backlog. When the reports say they lost some, the backlog is
/// stale by an unknown amount, so the watch invalidates then too.
/// </remarks>
public sealed class ProjectWatcher : IDisposable
{
    private readonly ProjectPath project;
    private readonly BacklogCache cache;
    private readonly TimeSpan quietPeriod;
    private readonly Timer quiet;
    private readonly IDisposable watch;

    public ProjectWatcher(ProjectPath project, BacklogCache cache, TimeSpan quietPeriod, IWriteReports reports)
    {
        this.project = project;
        this.cache = cache;
        this.quietPeriod = quietPeriod;
        quiet = new Timer(_ => this.cache.InvalidateFromWatch(this.project));
        watch = reports.Start(project.BeadsDirectory, StartTheQuietPeriodAgain, StartTheQuietPeriodAgain);
    }

    private void StartTheQuietPeriodAgain() => quiet.Change(quietPeriod, Timeout.InfiniteTimeSpan);

    public void Dispose()
    {
        watch.Dispose();
        quiet.Dispose();
    }
}
