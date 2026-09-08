using TracerUi.Core.Projects;

namespace TracerUi.Tests.Projects;

public class ProjectPathTests
{
    [Fact]
    public void TreatsAPathWithATrailingSeparatorAsTheSamePath()
    {
        var plain = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "tracer"));
        var trailing = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "tracer") + Path.DirectorySeparatorChar);

        Assert.Equal(plain, trailing);
        Assert.Equal(plain.GetHashCode(), trailing.GetHashCode());
    }

    [Fact]
    public void TreatsARelativeStepAsTheSamePath()
    {
        var plain = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "tracer"));
        var roundabout = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "widgets", "..", "tracer"));

        Assert.Equal(plain, roundabout);
    }

    [Fact]
    public void GivesTheNameOfTheDirectoryForTheSwitcher()
    {
        var path = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "tracer"));

        Assert.Equal("tracer", path.DirectoryName);
    }
}
