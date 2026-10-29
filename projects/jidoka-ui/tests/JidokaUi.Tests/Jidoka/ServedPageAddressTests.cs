using JidokaUi.Core.Beads;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Jidoka;

public sealed class ServedPageAddressTests
{
    [Fact]
    public void NamesTheKindTheBeadAndTheProjectThatHoldsIt()
    {
        var bead = new BeadAddress(ProjectPath.From("/work/shop front"), "b-7");

        Assert.Equal(
            "jidoka-page/question/b-7?project=%2Fwork%2Fshop%20front",
            ServedPageAddress.Of(JidokaPageKind.Question, bead));
    }

    [Fact]
    public void GivesTheDirectoryThatTheRouterMatchesBeforeTheIdForEachKind()
    {
        Assert.Equal("jidoka-page/gate", ServedPageAddress.DirectoryOf(JidokaPageKind.Gate));
    }
}
