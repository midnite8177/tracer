using JidokaUi.Core.Beads;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Jidoka;

public sealed class ServedPageAddressTests
{
    [Fact]
    public void NamesTheKindTheBeadAndTheProjectThatHoldsIt()
    {
        var tempFolder = Path.TrimEndingDirectorySeparator(Path.GetTempPath());
        var project = ProjectPath.From(Path.Combine(tempFolder, "shop front"));
        var bead = new BeadAddress(project, "b-7");
        var escapedSeparator = Path.DirectorySeparatorChar == '/' ? "%2F" : "%5C";

        Assert.Equal(
            $"jidoka-page/question/b-7?project={Uri.EscapeDataString(tempFolder)}{escapedSeparator}shop%20front",
            ServedPageAddress.Of(JidokaPageKind.Question, bead));
    }

    [Fact]
    public void GivesTheDirectoryThatTheRouterMatchesBeforeTheIdForEachKind()
    {
        Assert.Equal("jidoka-page/gate", ServedPageAddress.DirectoryOf(JidokaPageKind.Gate));
    }
}
