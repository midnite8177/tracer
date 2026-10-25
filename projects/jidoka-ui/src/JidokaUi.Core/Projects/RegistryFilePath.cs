namespace JidokaUi.Core.Projects;

public static class RegistryFilePath
{
    private const string ApplicationDirectoryName = "jidoka-ui";
    private const string EarlierApplicationDirectoryName = "tracer-ui";
    private const string FileName = "projects.json";

    /// <summary>Names projects.json, inside a jidoka-ui directory of the one it is given.</summary>
    public static string In(string userConfigurationDirectory) =>
        Path.Combine(userConfigurationDirectory, ApplicationDirectoryName, FileName);

    public static string EarlierIn(string userConfigurationDirectory) =>
        Path.Combine(userConfigurationDirectory, EarlierApplicationDirectoryName, FileName);
}
