namespace TracerUi.Core.Projects;

/// <summary>The projects that the person added to the app, and the filters that the person saved.</summary>
public sealed record ProjectRegistry(IReadOnlyList<ProjectPath> Projects, IReadOnlyList<SavedFilter> SavedFilters)
{
    public static ProjectRegistry Empty { get; } = new([], []);

    /// <summary>This registry with the project added, or nothing when it holds the project already.</summary>
    public ProjectRegistry? Adding(ProjectPath project) =>
        Projects.Contains(project) ? null : this with { Projects = [.. Projects, project] };
}
