using JidokaUi.Core.Beads;

namespace JidokaUi.Core.Projects;

/// <summary>The projects that the person added, and the rules that guard the additions.</summary>
public sealed class ProjectCatalog
{
    private readonly IProjectRegistryStore store;
    private readonly BdAdapter bd;

    public ProjectCatalog(IProjectRegistryStore store, BdAdapter bd)
    {
        this.store = store;
        this.bd = bd;
    }

    public IReadOnlyList<ProjectPath> Projects() => store.Load().Projects;

    public ProjectPath? Find(ProjectPath path) => Projects().FirstOrDefault(candidate => candidate.Equals(path));

    /// <summary>Every project of the registry, as the project picker shows them.</summary>
    /// <remarks>
    /// Whether two projects carry one directory name is a fact about the registry, so the catalog
    /// answers it and the chrome does not. Two names that differ in case alone count as one name,
    /// because the eye reads them as one.
    /// </remarks>
    public IReadOnlyList<ProjectEntry> Entries()
    {
        var projects = Projects();
        var counts = projects
            .GroupBy(project => project.DirectoryName, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(group => group.Key, group => group.Count(), StringComparer.OrdinalIgnoreCase);

        return [.. projects.Select(project => new ProjectEntry(project, counts[project.DirectoryName] > 1))];
    }

    /// <summary>Adds a project after both checks pass: the .beads directory exists, and bd answers there.</summary>
    public async Task<ProjectPathValidation> AddAsync(string candidatePath)
    {
        var validation = ProjectPathValidator.Validate(candidatePath);
        if (!validation.IsValid)
        {
            return validation;
        }

        var path = ProjectPath.From(candidatePath);
        if (Find(path) is not null)
        {
            return AlreadyThere;
        }

        var outcome = await bd.ReadyAsync(path);
        if (!outcome.Answered)
        {
            return ProjectPathValidation.Invalid($"bd does not answer in this directory. {outcome.Message}");
        }

        var update = store.Update(registry => registry.Adding(path));
        return update switch
        {
            RegistryUpdate.Written => ProjectPathValidation.Valid(),
            RegistryUpdate.Unchanged => AlreadyThere,
            RegistryUpdate.Busy => ProjectPathValidation.Invalid(RegistryBusy.Message),
            var other => throw new ArgumentOutOfRangeException(nameof(update), other, "This update has no outcome."),
        };
    }

    private static ProjectPathValidation AlreadyThere =>
        ProjectPathValidation.Invalid("This project is in the registry already.");
}
