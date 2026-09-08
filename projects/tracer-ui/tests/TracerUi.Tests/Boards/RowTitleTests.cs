using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Boards;

/// <summary>
/// The title of a row, which the board and the needs-you view both draw. It is a link, and it
/// hands its own press to the row that holds it, so one press opens one bead.
/// </summary>
public sealed class RowTitleTests : BunitContext
{
    [Fact]
    public void LetsAPressOnTheTitleReachTheRowThatHoldsIt()
    {
        var opened = new List<MouseEventArgs>();
        var row = TheRowThatHoldsATitleAndReportsTo(opened);

        APress.GoesDownAndClicksOn(() => row.Find("tr"), () => row.Find("a"), APress.Plain);

        Assert.Single(opened);
    }

    [Fact]
    public void DrawsTheClassTheAddressTheTooltipAndTheTextThatTheViewGivesIt()
    {
        var title = Render<RowTitle>(built => built
            .Add(c => c.Class, "board-title")
            .Add(c => c.Address, "bead/a-1")
            .Add(c => c.Tooltip, "Decide the licence")
            .Add(c => c.Text, "Decide the licence"));

        Assert.Equal("board-title", title.Find("a").GetAttribute("class"));
        Assert.Equal("bead/a-1", title.Find("a").GetAttribute("href"));
        Assert.Equal("Decide the licence", title.Find("a").GetAttribute("title"));
        Assert.Equal("Decide the licence", title.Find("a").TextContent);
    }

    [Fact]
    public void DrawsNoTooltipOnATitleThatStatesNone()
    {
        var title = Render<RowTitle>(built => built
            .Add(c => c.Class, "needs-you-title")
            .Add(c => c.Address, "bead/a-1")
            .Add(c => c.Tooltip, null)
            .Add(c => c.Text, "Decide the licence"));

        Assert.False(title.Find("a").HasAttribute("title"));
    }

    // A row that holds one title and records every release which opens its bead.
    private IRenderedComponent<PressableRow> TheRowThatHoldsATitleAndReportsTo(List<MouseEventArgs> opened) =>
        Render<PressableRow>(row => row
            .Add(c => c.Class, "a-row")
            .Add(c => c.Style, null)
            .Add(c => c.OnOpen, release => opened.Add(release))
            .Add(c => c.ChildContent, TheTitleInACell));

    // The one cell of the row, which holds the title. A row holds cells and nothing else, so a
    // title that stands outside one reaches no browser.
    private static readonly RenderFragment TheTitleInACell = cell =>
    {
        cell.OpenElement(0, "td");
        cell.OpenComponent<RowTitle>(1);
        cell.AddComponentParameter(2, nameof(RowTitle.Class), "a-title");
        cell.AddComponentParameter(3, nameof(RowTitle.Address), "bead/a-1");
        cell.AddComponentParameter(4, nameof(RowTitle.Tooltip), null);
        cell.AddComponentParameter(5, nameof(RowTitle.Text), "Decide the licence");
        cell.CloseComponent();
        cell.CloseElement();
    };
}
