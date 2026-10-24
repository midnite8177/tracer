namespace TracerUi.Core.Projects;

/// <summary>Reads and writes the registry of projects.</summary>
public interface IProjectRegistryStore
{
    ProjectRegistry Load();

    /// <summary>
    /// Reads the registry, applies the change, and writes what the change gives, with no other update
    /// between the read and the write. A change that returns null leaves the registry as it is.
    /// </summary>
    RegistryUpdate Update(Func<ProjectRegistry, ProjectRegistry?> change);
}
