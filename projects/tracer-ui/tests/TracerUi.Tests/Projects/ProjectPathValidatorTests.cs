using TracerUi.Core.Projects;

namespace TracerUi.Tests.Projects;

public class ProjectPathValidatorTests
{
    [Fact]
    public void AcceptsADirectoryThatContainsABeadsDirectory()
    {
        using var temp = new TempDirectory();
        var repository = temp.CreateSubdirectory("repository");
        Directory.CreateDirectory(Path.Combine(repository, ".beads"));

        var result = ProjectPathValidator.Validate(repository);

        Assert.True(result.IsValid);
    }

    [Fact]
    public void RejectsADirectoryThatHasNoBeadsDirectory()
    {
        using var temp = new TempDirectory();
        var repository = temp.CreateSubdirectory("repository");

        var result = ProjectPathValidator.Validate(repository);

        Assert.False(result.IsValid);
        Assert.Contains(".beads", result.Message);
    }

    [Fact]
    public void RejectsAPathThatDoesNotExistWithItsOwnMessage()
    {
        using var temp = new TempDirectory();
        var absent = Path.Combine(temp.Path, "no-such-directory");

        var result = ProjectPathValidator.Validate(absent);

        Assert.False(result.IsValid);
        Assert.Contains("does not exist", result.Message);
    }

    [Theory]
    [InlineData("")]
    [InlineData("   ")]
    public void RejectsABlankPathAndAsksForASelection(string blank)
    {
        var result = ProjectPathValidator.Validate(blank);

        Assert.False(result.IsValid);
        Assert.Contains("Select a directory", result.Message);
    }
}
