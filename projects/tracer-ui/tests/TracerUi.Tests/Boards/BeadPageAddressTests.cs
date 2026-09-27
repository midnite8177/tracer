using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Boards;

public sealed class BeadPageAddressTests
{
    private static readonly ProjectPath Project = ProjectPath.From(Path.Combine(Path.GetTempPath(), "second"));

    [Fact]
    public void NamesTheProjectThatHoldsTheBeadInTheQuery()
    {
        Assert.Equal(
            $"bead/b-7?project={Uri.EscapeDataString(Project.Value)}",
            BeadPageAddress.Of(new BeadAddress(Project, "b-7")));
    }

    [Fact]
    public void ReadsBackTheProjectThatItWroteIntoAnAddress()
    {
        var address = "http://localhost/" + BeadPageAddress.Of(new BeadAddress(Project, "b-7"));

        Assert.Equal(new ProjectInTheAddress.Named(Project), ProjectInTheAddress.Of(address));
    }
}
