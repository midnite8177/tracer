namespace TracerUi.Core.Look;

/// <summary>
/// What the browser did with the last ask of a row press for a new tab, and why the page says
/// anything about it. One page holds one of these, because one press answers at a time. It starts
/// empty, and a page that opens claims no press.
/// </summary>
public sealed class NewTabFeedback
{
    /// <summary>What the browser did with the last release that reached it.</summary>
    public NewTabOutcome Outcome { get; private set; } = NewTabOutcome.None;

    /// <summary>
    /// Why the tab that a person asked for is not there, in the words that the page shows on the
    /// screen, and what the person can do instead. A release that put the bead in front of the
    /// person carries no reason at all.
    /// </summary>
    public string? Reason => Outcome == NewTabOutcome.Refused
        ? "The browser would not open a new tab. Allow the popups of this page, or press the row again without a key."
        : null;

    /// <summary>
    /// Records what the browser did with a release. Every release records, so the reason of a
    /// refusal leaves the screen as soon as another press opens a bead.
    /// </summary>
    public void Take(NewTabOutcome what) => Outcome = what;
}
