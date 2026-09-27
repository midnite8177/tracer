using Bunit;
using Microsoft.AspNetCore.Components;

namespace TracerUi.Tests.Boards;

/// <summary>The epic picker as a person meets it, on whichever surface draws one.</summary>
public static class AnEpicPicker
{
    /// <summary>The id of the epic that the picker with this id holds, or an empty string for none.</summary>
    public static string ThePickedEpic<TSurface>(IRenderedComponent<TSurface> surface, string pickerId)
        where TSurface : class, IComponent =>
        surface.Find($"#{pickerId}").GetAttribute("value") ?? string.Empty;
}
