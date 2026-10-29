using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Factory;

/// <summary>
/// The epics of one project that the factory holds, or the reason that bd gave none of them.
/// </summary>
/// <param name="Reason">Empty when bd answered; otherwise a message for the person.</param>
public sealed record FactoryProject(ProjectPath Project, IReadOnlyList<FactoryEpic> Epics, string Reason)
{
    /// <summary>True when bd gave no beads for this project, and the reason says why.</summary>
    public bool IsUnread => Reason.Length > 0;
}

/// <summary>
/// Every epic that the factory holds, from every project of the registry, in the order that the
/// registry holds the projects. One project that bd does not answer for hides no other project, so
/// the view holds an entry for that project too and names the reason.
/// </summary>
public sealed record FactoryView(IReadOnlyList<FactoryProject> Projects)
{
    public bool IsEmpty => Projects.All(project => project.Epics.Count == 0);

    /// <summary>
    /// This view, with another read of one project in the place that the project already holds. A
    /// project that this view does not hold changes nothing.
    /// </summary>
    public FactoryView With(FactoryProject read) =>
        new([.. Projects.Select(project => project.Project.Equals(read.Project) ? read : project)]);
}

/// <summary>
/// Builds the factory view. It asks each project of the registry for its backlog and keeps the open
/// epics that carry the factory label, each with the lap of every task it holds.
/// </summary>
public sealed class FactoryReader
{
    private readonly ProjectCatalog catalog;
    private readonly BacklogCache backlogs;

    public FactoryReader(ProjectCatalog catalog, BacklogCache backlogs)
    {
        this.catalog = catalog;
        this.backlogs = backlogs;
    }

    /// <summary>
    /// Reads every project of the registry at once, and gives them back in the order that the
    /// registry holds them.
    /// </summary>
    public async Task<FactoryView> ReadAsync()
    {
        var reads = catalog.Projects().Select(ReadAsync).ToList();
        return new FactoryView(await Task.WhenAll(reads));
    }

    /// <summary>Reads one project alone, for a view that a change in that project made stale.</summary>
    public async Task<FactoryProject> ReadAsync(ProjectPath project)
    {
        var outcome = await backlogs.ReadAsync(project);
        if (!outcome.Answered)
        {
            return new FactoryProject(project, [], outcome.Message);
        }

        var backlog = outcome.Backlog;
        var held = backlog.Epics
            .Where(epic => !epic.IsClosed)
            .Select(epic => FactoryEpic.Of(backlog, epic))
            .OfType<FactoryEpic>();
        return new FactoryProject(project, [.. held], string.Empty);
    }
}
