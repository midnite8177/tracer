using TracerUi.Core.Projects;

namespace TracerUi.Tests.Projects;

/// <summary>A registry store that a test drives without a file on disk.</summary>
public sealed class InMemoryProjectRegistryStore : IProjectRegistryStore
{
    private ProjectRegistry registry = ProjectRegistry.Empty;

    /// <summary>How many times the code under test wrote a registry.</summary>
    public int Saves { get; private set; }

    /// <summary>
    /// True while another copy of the app holds the registry, so that every update answers busy and
    /// changes nothing.
    /// </summary>
    public bool Busy { get; set; }

    /// <summary>Puts this registry in the store, as a write from outside the code under test would.</summary>
    public void Hold(ProjectRegistry registry) => this.registry = registry;

    public ProjectRegistry Load() => registry;

    public RegistryUpdate Update(Func<ProjectRegistry, ProjectRegistry?> change)
    {
        if (Busy)
        {
            return RegistryUpdate.Busy;
        }

        if (change(registry) is not { } changed)
        {
            return RegistryUpdate.Unchanged;
        }

        registry = changed;
        Saves++;
        return RegistryUpdate.Written;
    }
}
