using TracerUi.Core.Boards;

namespace TracerUi.Core.Projects;

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
    public void Save(ProjectPath project, string name, BoardFilter filter)
    {
        var registry = store.Load();
        store.Save(registry with { SavedFilters = [.. Without(registry, project, name), new SavedFilter(project, name, filter)] });
    }

    /// <summary>Forgets the filter that this name holds in this project. It does nothing when no filter has the name.</summary>
    public void Remove(ProjectPath project, string name)
    {
        var registry = store.Load();
        var kept = Without(registry, project, name);
        if (kept.Length == registry.SavedFilters.Count)
        {
            return;
        }

        store.Save(registry with { SavedFilters = kept });
    }

    private static SavedFilter[] Without(ProjectRegistry registry, ProjectPath project, string name) =>
        [.. registry.SavedFilters.Where(saved => !Is(saved, project, name))];

    private static bool Is(SavedFilter saved, ProjectPath project, string name) =>
        saved.Project.Equals(project) && string.Equals(saved.Name, name, StringComparison.OrdinalIgnoreCase);
}
