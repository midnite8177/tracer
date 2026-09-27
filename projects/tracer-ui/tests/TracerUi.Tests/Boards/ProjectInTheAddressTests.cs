using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class ProjectInTheAddressTests
{
    [Fact]
    public void NamesNoProjectWhenTheQueryCarriesNone()
    {
        Assert.IsType<ProjectInTheAddress.None>(ProjectInTheAddress.Of("http://localhost/bead/b-7"));
    }

    [Fact]
    public void NamesNoProjectWhenTheProjectInTheQueryHasNoValue()
    {
        Assert.IsType<ProjectInTheAddress.None>(ProjectInTheAddress.Of("http://localhost/board?project=&type=bug"));
    }

    [Fact]
    public void TellsTextThatIsNoProjectPathApartFromAnAddressThatNamesNoProject()
    {
        Assert.Equal(
            new ProjectInTheAddress.NoPath("garbage"),
            ProjectInTheAddress.Of("http://localhost/bead/b-7?project=garbage"));
    }

    [Fact]
    public void TellsARelativePathApartFromAProjectThatTheAddressNames()
    {
        Assert.Equal(
            new ProjectInTheAddress.NoPath("someone/tracer"),
            ProjectInTheAddress.Of("http://localhost/board?project=someone%2Ftracer"));
    }
}
