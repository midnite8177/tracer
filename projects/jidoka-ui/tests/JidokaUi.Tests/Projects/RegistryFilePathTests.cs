using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Projects;

public class RegistryFilePathTests
{
    [Fact]
    public void PutsTheRegistryFileInAnApplicationDirectoryUnderTheUserConfigurationDirectory()
    {
        var userConfigurationDirectory = Path.Combine("/Users", "someone", ".config");

        var filePath = RegistryFilePath.In(userConfigurationDirectory);

        Assert.StartsWith(userConfigurationDirectory, filePath);
        Assert.Equal("projects.json", Path.GetFileName(filePath));
        Assert.Equal("jidoka-ui", Path.GetFileName(Path.GetDirectoryName(filePath)));
    }

    [Fact]
    public void PutsTheEarlierRegistryFileInTheDirectoryOfTheEarlierNameBesideTheApplicationDirectory()
    {
        var userConfigurationDirectory = Path.Combine("/Users", "someone", ".config");

        var filePath = RegistryFilePath.EarlierIn(userConfigurationDirectory);

        Assert.Equal(Path.Combine(userConfigurationDirectory, "tracer-ui", "projects.json"), filePath);
    }
}
