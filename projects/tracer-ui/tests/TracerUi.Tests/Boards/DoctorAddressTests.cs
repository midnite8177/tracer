using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Boards;

public sealed class DoctorAddressTests
{
    private static readonly ProjectPath Project =
        ProjectPath.From(Path.Combine(Path.GetTempPath(), "a project & more"));

    [Fact]
    public void NamesTheProjectInTheQuery()
    {
        Assert.Equal(
            $"doctor?project={Uri.EscapeDataString(Project.Value)}",
            DoctorAddress.Of(Project));
    }

    [Fact]
    public void ReadsBackTheProjectThatItWroteIntoAnAddress()
    {
        var address = "http://localhost/" + DoctorAddress.Of(Project);

        Assert.Equal(new ProjectInTheAddress.Named(Project), ProjectInTheAddress.Of(address));
    }

    [Fact]
    public void IsThePlainDoctorAddressWhenThereIsNoProject()
    {
        var address = "http://localhost/" + DoctorAddress.Of(null);

        Assert.Equal("doctor", DoctorAddress.Of(null));
        Assert.Equal(new ProjectInTheAddress.None(), ProjectInTheAddress.Of(address));
    }
}
