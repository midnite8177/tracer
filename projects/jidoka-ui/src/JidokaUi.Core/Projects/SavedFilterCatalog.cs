using JidokaUi.Core.Boards;

namespace JidokaUi.Core.Projects;

/// <summary>
/// The filters that the person saved. They live in the registry file beside the projects, so they
/// outlast the app, and one project and one name together hold one filter.
/// </summary>
public sealed class SavedFilterCatalog
{
    private readonly IProjectRegistryStore store;

    public SavedFilterCatalog(IProjectRegistryStore store)
    {
        this.store = store;
    }

    /// <summary>The filters that the person saved in this project, in the order that they saved them.</summary>
    public IReadOnlyList<SavedFilter> Filters(ProjectPath project) =>
        [.. store.Load().SavedFilters.Where(saved => saved.Project.Equals(project))];

    /// <summary>
    /// Keeps this filter in this project under this name, and replaces the filter that the name held
    /// there before. The same name in another project holds its own filter.
    /// </summary>
    public RegistryUpdate Save(ProjectPath project, string name, BoardFilter filter) =>
        store.Update(registry =>
            registry with { SavedFilters = [.. Without(registry, project, name), new SavedFilter(project, name, filter)] });

    /// <summary>Forgets the filter that this name holds in this project. It writes nothing when no filter has the name.</summary>
    public RegistryUpdate Remove(ProjectPath project, string name) =>
        store.Update(registry =>
        {
            var kept = Without(registry, project, name);
            return kept.Length == registry.SavedFilters.Count ? null : registry with { SavedFilters = kept };
        });

    private static SavedFilter[] Without(ProjectRegistry registry, ProjectPath project, string name) =>
        [.. registry.SavedFilters.Where(saved => !Is(saved, project, name))];

    private static bool Is(SavedFilter saved, ProjectPath project, string name) =>
        saved.Project.Equals(project) && string.Equals(saved.Name, name, StringComparison.OrdinalIgnoreCase);
}
