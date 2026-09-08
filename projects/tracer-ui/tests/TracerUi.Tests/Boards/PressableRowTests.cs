using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Boards;

/// <summary>
/// The row that answers a row press, which the board and the needs-you view both draw. It says
/// what a press means: which press opens the bead of the row, and which press opens nothing.
/// </summary>
public sealed class PressableRowTests : BunitContext
{
    [Fact]
    public void OpensTheBeadWhenAPressComesUpWhereItWentDown()
    {
        var opened = new List<MouseEventArgs>();
        var row = APressableRow.ThatReportsTo(this, opened);

        APress.GoesDownAndClicksOn(() => row.Find("tr"), () => row.Find("tr"), APress.Plain);

        Assert.Single(opened);
    }

    [Fact]
    public void OpensNothingWhenAPressTravelsAcrossTheRow()
    {
        var opened = new List<MouseEventArgs>();
        var row = APressableRow.ThatReportsTo(this, opened);

        APress.GoesDownOn(() => row.Find("tr"), APress.Plain);
        row.Find("tr").Click(APress.Beside(APress.Plain, APress.TheTravelOfADrag));

        Assert.Empty(opened);
    }

    [Fact]
    public void OpensTheBeadWhenTheMiddleButtonReleasesOnTheRow()
    {
        var opened = new List<MouseEventArgs>();
        var row = APressableRow.ThatReportsTo(this, opened);

        row.Find("tr").MouseUp(APress.OfTheMiddleButton);

        Assert.Single(opened);
    }

    [Fact]
    public void OpensTheBeadOnceWhenThePrimaryButtonReleasesOnTheRowAndTheClickFollowsIt()
    {
        var opened = new List<MouseEventArgs>();
        var row = APressableRow.ThatReportsTo(this, opened);

        APress.LandsOn(() => row.Find("tr"), APress.Plain);

        Assert.Single(opened);
    }

    [Fact]
    public void DrawsTheClassTheStyleAndTheCellsThatThePageGivesIt()
    {
        var row = Render<PressableRow>(built => built
            .Add(c => c.Class, "board-row")
            .Add(c => c.Style, "--row-depth: 2")
            .Add(c => c.OnOpen, EventCallback.Factory.Create<MouseEventArgs>(this, () => { }))
            .AddChildContent("<td>Decide the licence</td>"));

        Assert.Equal("board-row", row.Find("tr").GetAttribute("class"));
        Assert.Equal("--row-depth: 2", row.Find("tr").GetAttribute("style"));
        Assert.Equal("Decide the licence", row.Find("tr td").TextContent);
    }

    [Fact]
    public void DrawsNoStyleOnARowThatStatesNone()
    {
        var row = APressableRow.ThatReportsTo(this, []);

        Assert.False(row.Find("tr").HasAttribute("style"));
    }
}
