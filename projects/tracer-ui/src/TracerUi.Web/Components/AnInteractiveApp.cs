using Microsoft.AspNetCore.Components.Web;

namespace TracerUi.Web.Components;

/// <summary>
/// The one render mode of the app. The whole router subtree is interactive, so no page can choose a
/// mode of its own, and the choice belongs here. It does not prerender: see ADR 0014.
/// </summary>
public static class AnInteractiveApp
{
    /// <summary>The mode that every root component of the app takes, and the only one it has.</summary>
    public static readonly InteractiveServerRenderMode WithoutPrerender = new(prerender: false);
}
