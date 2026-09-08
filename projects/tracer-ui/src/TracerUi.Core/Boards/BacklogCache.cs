using System.Collections.Concurrent;
using TracerUi.Core.Beads;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The one copy of each project's backlog that the app holds in memory. A read gives the held copy,
/// so a board that a person rebuilds costs no run of bd. An invalidation drops the copy of one
/// project, and the next read of that project asks bd again. A write of this app invalidates the
/// project that it wrote to, so a person sees the result of an action of their own.
/// </summary>
public sealed class BacklogCache
{
    private readonly BacklogReader reader;

    private readonly ConcurrentDictionary<ProjectPath, Lazy<Task<BacklogOutcome>>> held = new();

    public BacklogCache(BacklogReader reader, BdAdapter adapter)
    {
        this.reader = reader;
        adapter.Wrote += Invalidate;
    }

    /// <summary>
    /// Names the project whose held backlog the cache dropped. A page that shows that project reads
    /// it again, so a person never looks at a board that a write already made stale.
    /// </summary>
    public event Action<ProjectPath>? Changed;

    /// <summary>
    /// The backlog of this project, from the held copy or from a read of bd. The cache holds an
    /// answer alone and drops a failure at once, so the next read asks bd again. A held failure
    /// would keep an error message on the board until something invalidated the project.
    /// </summary>
    public async Task<BacklogOutcome> ReadAsync(ProjectPath project)
    {
        var entry = held.GetOrAdd(
            project,
            path => new Lazy<Task<BacklogOutcome>>(() => reader.ReadAsync(path)));
        var outcome = await entry.Value;
        if (!outcome.Answered)
        {
            held.TryRemove(new KeyValuePair<ProjectPath, Lazy<Task<BacklogOutcome>>>(project, entry));
        }

        return outcome;
    }

    /// <summary>Drops the held backlog of one project. Every other project keeps its own.</summary>
    public void Invalidate(ProjectPath project)
    {
        held.TryRemove(project, out _);
        Changed?.Invoke(project);
    }
}
