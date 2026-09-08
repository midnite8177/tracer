using TracerUi.Core.Beads;

namespace TracerUi.Tests.Beads;

public sealed class BeadLabelTests
{
    [Fact]
    public void ReadsAWordWithBlankAroundItAsTheWordAlone()
    {
        var made = BeadLabel.TryFrom("  human  ", out var label);

        Assert.True(made);
        Assert.NotNull(label);
        Assert.Equal("human", label.Word);
    }

    [Fact]
    public void RefusesAWordThatIsAllBlank()
    {
        var made = BeadLabel.TryFrom("   ", out var label);

        Assert.False(made);
        Assert.Null(label);
    }
}
