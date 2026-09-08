using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The beads of one project that wait on a person, or the reason that bd gave none of them.
/// </summary>
/// <param name="Reason">Empty when bd answered; otherwise a message for the person.</param>
public sealed record NeedsYouProject(ProjectPath Project, IReadOnlyList<Bead> Beads, string Reason)
{
    /// <summary>True when bd gave no beads for this project, and the reason says why.</summary>
    public bool IsUnread => Reason.Length > 0;
}

/// <summary>
/// Every bead that waits on a person, from every project of the registry, in the order that the
/// registry holds the projects. One project that bd does not answer for hides no other project, so
/// the view holds an entry for that project too and names the reason.
/// </summary>
public sealed record NeedsYouView(IReadOnlyList<NeedsYouProject> Projects)
{
    public bool IsEmpty => Projects.All(project => project.Beads.Count == 0);

    /// <summary>
    /// This view, with another read of one project in the place that the project already holds. A
    /// project that this view does not hold changes nothing, because a change in one project leaves
    /// every other project as it was.
    /// </summary>
    public NeedsYouView With(NeedsYouProject read) =>
        new([.. Projects.Select(project => project.Project.Equals(read.Project) ? read : project)]);
}

/// <summary>
/// Builds the needs-you view. It asks each project of the registry for its backlog and keeps the
/// beads that the built-in needs-you filter keeps, so one project and every project answer the same
/// question.
/// </summary>
public sealed class NeedsYouReader
{
    private readonly ProjectCatalog catalog;
    private readonly BacklogCache backlogs;

    public NeedsYouReader(ProjectCatalog catalog, BacklogCache backlogs)
    {
        this.catalog = catalog;
        this.backlogs = backlogs;
    }

    /// <summary>Reads every project of the registry, in the order that the registry holds them.</summary>
    public async Task<NeedsYouView> ReadAsync()
    {
        var projects = new List<NeedsYouProject>();
        foreach (var project in catalog.Projects())
        {
            projects.Add(await ReadAsync(project));
        }

        return new NeedsYouView(projects);
    }

    /// <summary>Reads one project alone, for a view that a change in that project made stale.</summary>
    public async Task<NeedsYouProject> ReadAsync(ProjectPath project)
    {
        var outcome = await backlogs.ReadAsync(project);
        return outcome.Answered
            ? new NeedsYouProject(project, outcome.Backlog.BeadsThatMatch(BoardFilter.NeedsYou), string.Empty)
            : new NeedsYouProject(project, [], outcome.Message);
    }
}
