namespace TracerUi.Core.Look;

/// <summary>
/// What the browser did with the ask of a row press for a new tab. A browser guards against a page
/// that opens tabs on its own, so no page knows that the tab opened until the browser answers.
/// </summary>
public enum NewTabOutcome
{
    /// <summary>
    /// The person stands where the press asked to stand, thus the page says nothing at all: the
    /// release asked for no new tab, or it asked for one and the browser opened it.
    /// </summary>
    None,

    /// <summary>The browser would not open the tab, so the person stays on the page they pressed.</summary>
    Refused,
}
