using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class DemoLineTests
{
    [Fact]
    public void ReadsTheDemoSectionOfADescriptionAsOneLine()
    {
        var description = """
            ## What

            Some background.

            ## Demo

            Open the board and see
            the beads as a tree of epics.

            ## Seams

            The view-model layer.
            """;

        Assert.Equal(
            "Open the board and see the beads as a tree of epics.",
            DemoLine.In(description));
    }

    [Fact]
    public void GivesAnEmptyLineForADescriptionThatHasNoDemoSection()
    {
        Assert.Equal(string.Empty, DemoLine.In("## What\n\nSome background.\n"));
    }
}
