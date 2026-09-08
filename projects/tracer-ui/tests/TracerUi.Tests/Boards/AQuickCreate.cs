using Bunit;
using Microsoft.AspNetCore.Components;
using TracerUi.Web.Components.Pages;

namespace TracerUi.Tests.Boards;

/// <summary>
/// The quick create as a person meets it, on whichever surface draws it. The board and the page of
/// an epic both answer to this, so a test of one reads the same way as a test of the other.
/// </summary>
public static class AQuickCreate
{
    public static IReadOnlyList<string> TheTypesItOffersSpelledOut { get; } =
        ["bug", "feature", "task", "chore", "decision"];

    public static IEnumerable<string> TheTypesItOffers<TSurface>(
        IRenderedComponent<TSurface> surface,
        string pickerId)
        where TSurface : class, IComponent =>
        surface.FindAll($"#{pickerId} option").Select(offered => offered.TextContent);

    public static string TheLabelOf<TSurface>(IRenderedComponent<TSurface> surface, string controlId)
        where TSurface : class, IComponent =>
        surface.Find($"label[for={controlId}]").TextContent.Trim();

    /// <summary>
    /// The one component that draws the fields of the quick create on this surface. A surface that
    /// wrote its own title box and type picker instead would draw none.
    /// </summary>
    public static IRenderedComponent<QuickCreateFields> TheFieldsOf<TSurface>(
        IRenderedComponent<TSurface> surface)
        where TSurface : class, IComponent =>
        surface.FindComponents<QuickCreateFields>().Single();
}
