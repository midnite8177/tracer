namespace TracerUi.Core.Beads;

/// <summary>The result of a write to bd: that it happened, or the reason it did not.</summary>
/// <param name="Wrote">True when bd made the change.</param>
/// <param name="Message">Empty when bd wrote; otherwise a message for the person.</param>
public sealed record BdWriteOutcome(bool Wrote, string Message)
{
    public static BdWriteOutcome Written() => new(true, string.Empty);

    public static BdWriteOutcome Failure(string message) => new(false, message);
}
