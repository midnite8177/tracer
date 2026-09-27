namespace TracerUi.Core.Projects;

/// <summary>
/// The project that one tab looks at. One selection lives per circuit, and it is the memory of the
/// tab: the last project that an address named or a pick made active. A reload starts a new circuit,
/// so it forgets that project, and only the address brings one back.
/// </summary>
public sealed class ActiveProjectSelection
{
    private readonly ProjectCatalog catalog;

    public ActiveProjectSelection(ProjectCatalog catalog)
    {
        this.catalog = catalog;
    }

    /// <summary>Says which project is active now, each time the active project becomes another one.</summary>
    public event Action<ProjectPath>? Changed;

    public ProjectPath? Current { get; private set; }

    /// <summary>Makes the project at this path the active one. Returns false when the registry has no such project.</summary>
    /// <remarks>A pick of the project that is active already changes nothing, so it raises no <see cref="Changed"/>.</remarks>
    public bool Select(ProjectPath path)
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
            Changed?.Invoke(project);
        }

        return true;
    }
}
