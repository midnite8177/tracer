using TracerUi.Core.Projects;

namespace TracerUi.Tests.Projects;

/// <summary>A registry store that a test drives without a file on disk.</summary>
public sealed class InMemoryProjectRegistryStore : IProjectRegistryStore
{
    private ProjectRegistry registry = ProjectRegistry.Empty;

    /// <summary>How many times the code under test saved a registry.</summary>
    public int Saves { get; private set; }

    public ProjectRegistry Load() => registry;

    public void Save(ProjectRegistry registry)
    {
        this.registry = registry;
        Saves++;
    }
}
