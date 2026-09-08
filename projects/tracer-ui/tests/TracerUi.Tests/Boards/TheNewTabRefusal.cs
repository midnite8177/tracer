using AngleSharp.Dom;
using Bunit;
using Microsoft.AspNetCore.Components;

namespace TracerUi.Tests.Boards;

/// <summary>
/// What a view says when the browser opened no tab that a press asked for. The board and the
/// needs-you view each draw it in one place, so a test of either asks for it the same way.
/// </summary>
public static class TheNewTabRefusal
{
    private const string WhereItIsDrawn = "p.new-tab-refusal";

    /// <summary>
    /// What the view said about the tab that the browser refused. It throws when the view drew
    /// no refusal, so a test that expects none asks <see cref="EveryOneOn"/> instead.
    /// </summary>
    public static string On<TView>(IRenderedComponent<TView> view)
        where TView : class, IComponent =>
        view.Find(WhereItIsDrawn).TextContent;

    /// <summary>Every refusal that the view drew, which is none when the browser opened the tab.</summary>
    public static IReadOnlyList<IElement> EveryOneOn<TView>(IRenderedComponent<TView> view)
        where TView : class, IComponent =>
        [.. view.FindAll(WhereItIsDrawn)];
}
