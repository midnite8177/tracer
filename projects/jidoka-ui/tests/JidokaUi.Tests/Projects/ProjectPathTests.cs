using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Projects;

public class ProjectPathTests
{
    [Fact]
    public void TreatsAPathWithATrailingSeparatorAsTheSamePath()
    {
        var plain = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "campfire"));
        var trailing = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "campfire") + Path.DirectorySeparatorChar);

        Assert.Equal(plain, trailing);
        Assert.Equal(plain.GetHashCode(), trailing.GetHashCode());
    }

    [Fact]
    public void TreatsARelativeStepAsTheSamePath()
    {
        var plain = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "campfire"));
        var roundabout = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "widgets", "..", "campfire"));

        Assert.Equal(plain, roundabout);
    }

    [Fact]
    public void GivesTheNameOfTheDirectoryForTheSwitcher()
    {
        var path = ProjectPath.From(Path.Combine("/Users", "someone", "Projects", "campfire"));

        Assert.Equal("campfire", path.DirectoryName);
    }

    [Fact]
    public void ReadsTextThatNamesAnAbsolutePath()
    {
        var text = Path.Combine(Path.GetTempPath(), "campfire");

        Assert.True(ProjectPath.TryFromAbsolute(text, out var path));
        Assert.Equal(ProjectPath.From(text), path);
    }

    [Fact]
    public void RefusesRelativeTextInsteadOfResolvingItAgainstTheWorkingDirectory()
    {
        Assert.False(ProjectPath.TryFromAbsolute(Path.Combine("someone", "campfire"), out _));
    }
}
