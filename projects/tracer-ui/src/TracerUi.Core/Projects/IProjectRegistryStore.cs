namespace TracerUi.Core.Projects;

/// <summary>Reads and writes the registry of projects.</summary>
public interface IProjectRegistryStore
{
    ProjectRegistry Load();

    void Save(ProjectRegistry registry);
}
