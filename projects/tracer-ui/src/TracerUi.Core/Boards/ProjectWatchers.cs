using System.Collections.Concurrent;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The watches that the app runs, one for each project that a person opened. A watch lasts for the
/// life of the app, because a person comes back to a project and the board must be current then too.
/// </summary>
public sealed class ProjectWatchers : IDisposable
{
    /// <summary>How long a watch waits after the last report of a write before it invalidates.</summary>
    public static readonly TimeSpan QuietPeriod = TimeSpan.FromMilliseconds(250);

    private readonly BacklogCache cache;

    private readonly ConcurrentDictionary<ProjectPath, Lazy<ProjectWatcher>> watching = new();

    public ProjectWatchers(BacklogCache cache)
    {
        this.cache = cache;
    }

    /// <summary>
    /// Starts the watch on this project, or keeps the one that already runs. A project whose .beads
    /// directory a person deleted gets no watch, and the board still reads it on demand.
    /// </summary>
    public void Watch(ProjectPath project)
    {
        if (!Directory.Exists(project.BeadsDirectory))
        {
            return;
        }

        _ = watching.GetOrAdd(
            project,
            path => new Lazy<ProjectWatcher>(() => new ProjectWatcher(path, cache, QuietPeriod))).Value;
    }

    public void Dispose()
    {
        foreach (var watcher in watching.Values)
        {
            watcher.Value.Dispose();
        }

        watching.Clear();
    }
}
