using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Look;

namespace TracerUi.Tests.Boards;

/// <summary>
/// The browser that a view asks for a new tab. A view opens one through a single call, and a
/// browser is free to refuse it, so a test plans the answer and then reads what the view opened.
/// </summary>
public static class ABrowser
{
    /// <summary>
    /// Plans the one call that opens a page beside this one, so a test reads the tabs that the
    /// browser opened. A view that asks for no tab leaves it empty.
    /// </summary>
    public static JSRuntimeInvocationHandler<bool> ThatOpensEveryTab(BunitContext context) =>
        context.JSInterop.Setup<bool>(NewTabCall.Name, _ => true).SetResult(true);

    /// <summary>
    /// Plans a browser that refuses every tab, as a browser that blocks the popups of a site does.
    /// </summary>
    public static JSRuntimeInvocationHandler<bool> ThatRefusesEveryTab(BunitContext context) =>
        context.JSInterop.Setup<bool>(NewTabCall.Name, _ => true).SetResult(false);

    /// <summary>The addresses that the browser opened beside this page, in the order it opened them.</summary>
    public static IReadOnlyList<string> TheAddressesOf(JSRuntimeInvocationHandler<bool> opened) =>
        [.. opened.Invocations[NewTabCall.Name].Select(call => call.Arguments[0] as string ?? string.Empty)];

    /// <summary>The address that the browser stands on, which an open of a bead in this tab changes.</summary>
    public static string TheAddressItStandsOn(BunitContext context) =>
        context.Services.GetRequiredService<NavigationManager>().Uri;
}
