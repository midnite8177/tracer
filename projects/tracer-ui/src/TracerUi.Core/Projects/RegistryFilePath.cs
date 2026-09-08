namespace TracerUi.Core.Projects;

public static class RegistryFilePath
{
    private const string ApplicationDirectoryName = "tracer-ui";
    private const string FileName = "projects.json";

    /// <summary>Names projects.json, inside a tracer-ui directory of the one it is given.</summary>
    public static string In(string userConfigurationDirectory) =>
        Path.Combine(userConfigurationDirectory, ApplicationDirectoryName, FileName);
}
