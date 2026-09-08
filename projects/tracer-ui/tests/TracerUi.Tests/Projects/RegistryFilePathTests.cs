using TracerUi.Core.Projects;

namespace TracerUi.Tests.Projects;

public class RegistryFilePathTests
{
    [Fact]
    public void PutsTheRegistryFileInAnApplicationDirectoryUnderTheUserConfigurationDirectory()
    {
        var userConfigurationDirectory = Path.Combine("/Users", "someone", ".config");

        var filePath = RegistryFilePath.In(userConfigurationDirectory);

        Assert.StartsWith(userConfigurationDirectory, filePath);
        Assert.Equal("projects.json", Path.GetFileName(filePath));
        Assert.Equal("tracer-ui", Path.GetFileName(Path.GetDirectoryName(filePath)));
    }
}
