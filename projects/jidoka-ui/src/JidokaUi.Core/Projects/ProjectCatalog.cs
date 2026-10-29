using JidokaUi.Core.Beads;

namespace JidokaUi.Core.Projects;

/// <summary>
/// The projects that the person added and the repos that jidoka onboarded, and the rules that guard
/// the additions.
/// </summary>
public sealed class ProjectCatalog
{
    private readonly IProjectRegistryStore store;
    private readonly BdAdapter bd;
    private readonly IOnboardedProjects onboarded;

    public ProjectCatalog(IProjectRegistryStore store, BdAdapter bd, IOnboardedProjects onboarded)
    {
        this.store = store;
        this.bd = bd;
        this.onboarded = onboarded;
    }

    /// <summary>
    /// The projects of the registry, then the onboarded repos that the registry does not hold. An
    /// onboarded repo whose folder has no .beads directory is left out, because the app cannot open
    /// it as a project.
    /// </summary>
    public IReadOnlyList<ProjectPath> Projects()
    {
        var added = store.Load().Projects;
        var listed = onboarded.Paths()
            .Where(path => !added.Contains(path) && Directory.Exists(path.BeadsDirectory));

        return [.. added, .. listed];
    }

    public ProjectPath? Find(ProjectPath path) => Projects().FirstOrDefault(candidate => candidate.Equals(path));

    /// <summary>Every project of the list, as the project picker shows them.</summary>
    /// <remarks>
    /// Whether two projects carry one directory name is a fact about the list, so the catalog
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
        if (store.Load().Projects.Contains(path))
        {
            return AlreadyThere;
        }

        if (Find(path) is not null)
        {
            return AlreadyOnboarded;
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

    private static ProjectPathValidation AlreadyOnboarded =>
        ProjectPathValidation.Invalid("jidoka onboarded this project, so the list holds it already.");

    private static ProjectPathValidation AlreadyThere =>
        ProjectPathValidation.Invalid("This project is in the registry already.");
}
