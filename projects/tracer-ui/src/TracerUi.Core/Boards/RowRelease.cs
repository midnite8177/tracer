namespace TracerUi.Core.Boards;

/// <summary>
/// The button and the modifier keys that the release of a row press carries. A person asks a
/// link for a new tab with the middle button or with a modifier key, and asks a row of the board or
/// of the needs-you view for one the same way, so the row reads the release before it decides where
/// the bead opens.
/// </summary>
public sealed record RowRelease(long Button, bool Control, bool Meta)
{
    /// <summary>The button of a plain press, which opens the bead in this tab.</summary>
    public const long PrimaryButton = 0;

    /// <summary>
    /// The button of the wheel, which every browser reads on a link as a new tab. It raises no
    /// click of its own, so a page that presses a row reads it on the release of the mouse.
    /// </summary>
    public const long MiddleButton = 1;

    /// <summary>
    /// True when this release asks for a new tab. The page then stays as it is, with its filter,
    /// its ticked beads and its collapsed rows, and the bead opens beside it.
    /// </summary>
    public bool AsksForANewTab => Button == MiddleButton || Control || Meta;
}
