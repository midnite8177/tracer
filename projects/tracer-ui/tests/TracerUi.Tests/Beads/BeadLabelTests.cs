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

    [Theory]
    [InlineData("docs")]
    [InlineData("DOCS")]
    [InlineData("Docs")]
    public void ReadsAWordThatDiffersFromItsOwnInCaseAloneAsTheSameLabel(string word)
    {
        Assert.True(BeadLabel.TryFrom("docs", out var label));

        Assert.True(label.ReadsTheSameAs(word));
    }

    [Fact]
    public void ReadsAnotherWordAsAnotherLabel()
    {
        Assert.True(BeadLabel.TryFrom("docs", out var label));

        Assert.False(label.ReadsTheSameAs("doc"));
    }

    [Fact]
    public void TakesATypedWordWithBlankAroundItAsTheWordAlone()
    {
        var made = BeadLabel.TryFromTyped("  spike ", out var label, out var whyNot);

        Assert.True(made);
        Assert.NotNull(label);
        Assert.Equal("spike", label.Word);
        Assert.Null(whyNot);
    }

    [Theory]
    [InlineData("   ", BeadLabel.NeedsAWord)]
    [InlineData("a,b", BeadLabel.HoldsNoComma)]
    [InlineData(" , ", BeadLabel.HoldsNoComma)]
    public void RefusesATypedWordThatNoLabelFlagCanSendAndSaysWhy(string typed, string reason)
    {
        var made = BeadLabel.TryFromTyped(typed, out var label, out var whyNot);

        Assert.False(made);
        Assert.Null(label);
        Assert.Equal(reason, whyNot);
    }
}
