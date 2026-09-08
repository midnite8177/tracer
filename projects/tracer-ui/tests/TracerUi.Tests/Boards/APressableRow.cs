using Bunit;
using Microsoft.AspNetCore.Components.Web;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Boards;

/// <summary>
/// A row that answers a press, rendered on its own with one cell of text. A test of what a press
/// means needs no page around the row, so it renders the row alone and reads what the press opened.
/// </summary>
public static class APressableRow
{
    /// <summary>
    /// The row, recording every release that opens its bead in the list that the test holds.
    /// </summary>
    public static IRenderedComponent<PressableRow> ThatReportsTo(
        BunitContext context, List<MouseEventArgs> opened) =>
        context.Render<PressableRow>(row => row
            .Add(c => c.Class, "a-row")
            .Add(c => c.Style, null)
            .Add(c => c.OnOpen, release => opened.Add(release))
            .AddChildContent("<td>Decide the licence</td>"));
}
