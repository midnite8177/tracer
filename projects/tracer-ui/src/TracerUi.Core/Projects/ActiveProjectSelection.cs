namespace TracerUi.Core.Projects;

/// <summary>The project that the person looks at now. One selection lives per browser session.</summary>
public sealed class ActiveProjectSelection
{
    private readonly ProjectCatalog catalog;

    public ActiveProjectSelection(ProjectCatalog catalog)
    {
        this.catalog = catalog;
    }

    /// <summary>The key that holds the path of the active project in the storage of one browser.</summary>
    public const string StorageKey = "tracer-ui.active-project";

    /// <summary>
    /// Says that the active project is another one now. The top bar switches the project from any
    /// page, and the browser gives its own choice back at the first render of a session, so a page
    /// that reads the active project learns of both here. The change says which one it is.
    /// </summary>
    public event Action<ActiveProjectChange>? Changed;

    public ProjectPath? Current { get; private set; }

    /// <summary>
    /// Makes the project at this stored path the active one. The browser holds the path, so the
    /// choice outlives a reload of the page. It gives false, and it leaves the active project as
    /// it is, for a browser that holds no path, for text that is no path, and for a path that the
    /// registry does not carry.
    /// </summary>
    public bool Restore(string? storedPath) =>
        !string.IsNullOrWhiteSpace(storedPath)
        && ProjectPath.TryFrom(storedPath, out var path)
        && MakeActive(path, ActiveProjectChangeKind.Restore);

    /// <summary>Makes the project at this path the active one. Returns false when the registry has no such project.</summary>
    /// <remarks>
    /// A pick of the project that is active already changes nothing, so it says nothing. A board
    /// that heard it would read every bead of that project again for no gain.
    /// </remarks>
    public bool Select(ProjectPath path) => MakeActive(path, ActiveProjectChangeKind.Switch);

    private bool MakeActive(ProjectPath path, ActiveProjectChangeKind kind)
    {
        var project = catalog.Find(path);
        if (project is null)
        {
            return false;
        }

        var becameAnotherOne = !project.Equals(Current);
        Current = project;
        if (becameAnotherOne)
        {
            Changed?.Invoke(new ActiveProjectChange(project, kind));
        }

        return true;
    }
}
