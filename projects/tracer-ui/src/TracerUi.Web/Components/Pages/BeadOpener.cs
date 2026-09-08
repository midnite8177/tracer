using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;
using TracerUi.Core.Boards;
using TracerUi.Core.Look;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// Opens a page where the release of a press asks for it: in this tab, or in a new tab beside it. A
/// row of the board and a row of the needs-you view are table rows and not links, so the browser
/// has nothing of its own to open and the app asks it. One type asks, thus both pages answer a
/// release the same way and neither of them states the call that the browser answers.
/// </summary>
public sealed class BeadOpener
{
    private readonly NavigationManager navigation;
    private readonly IJSRuntime js;

    public BeadOpener(NavigationManager navigation, IJSRuntime js)
    {
        this.navigation = navigation;
        this.js = js;
    }

    /// <summary>
    /// Opens the page at this address where the release asks for it, and says what the browser did.
    /// A browser is free to refuse the new tab, so a caller that asked for one reads the answer and
    /// tells the person what happened.
    /// </summary>
    public async Task<NewTabOutcome> OpenAsync(string address, MouseEventArgs release)
    {
        if (new RowRelease(release.Button, release.CtrlKey, release.MetaKey).AsksForANewTab)
        {
            return await js.InvokeAsync<bool>(NewTabCall.Name, address)
                ? NewTabOutcome.None
                : NewTabOutcome.Refused;
        }

        navigation.NavigateTo(address);
        return NewTabOutcome.None;
    }
}
