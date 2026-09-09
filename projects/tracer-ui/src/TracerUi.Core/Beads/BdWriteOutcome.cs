namespace TracerUi.Core.Beads;

/// <summary>The result of a write to bd: that it happened, or the reason it did not.</summary>
/// <param name="Wrote">True when bd made the change.</param>
/// <param name="Message">Empty when bd wrote; otherwise a message for the person.</param>
/// <param name="GaveUp">True when the app stopped waiting on bd, so this write may still have landed.</param>
public sealed record BdWriteOutcome(bool Wrote, string Message, bool GaveUp)
{
    public static BdWriteOutcome Written() => new(true, string.Empty, false);

    public static BdWriteOutcome Failure(string message) => new(false, message, false);

    public static BdWriteOutcome Abandoned(string message) => new(false, message, true);
}
