using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>Where a change to a project's held backlog came from.</summary>
public enum BacklogChangeKind
{
    /// <summary>A write of this app changed the project. A page that reads it again is a re-read.</summary>
    Write,

    /// <summary>The project watcher saw its .beads directory change on its own.</summary>
    Watch,
}

/// <summary>
/// The project whose held backlog the cache dropped, and what caused it. A page distinguishes a
/// re-read of its own write from a change the project watcher raised by reading <see cref="Kind"/>.
/// </summary>
/// <param name="Project">The project whose held backlog the cache dropped.</param>
/// <param name="Kind">Whether a write of this app caused the drop, or the project watcher did.</param>
public sealed record BacklogChange(ProjectPath Project, BacklogChangeKind Kind)
{
    /// <summary>True when the next read of this change is a re-read, because this app wrote it.</summary>
    public bool IsReRead => Kind == BacklogChangeKind.Write;
}
