namespace TracerUi.Core.Beads;

/// <summary>
/// The result of a create: whether the bead exists now, and the id that bd gave it. A create can
/// take more than one write, so a bead can exist and the message still say what went wrong after
/// bd made it. The message is what the person reads, whatever the app made.
/// </summary>
/// <param name="Created">True when the bead exists.</param>
/// <param name="Message">Empty when every write of the create ran; otherwise a message for the person.</param>
/// <param name="Id">The id that bd gave the new bead, or an empty string when bd made none.</param>
public sealed record BdCreateOutcome(bool Created, string Message, string Id)
{
    public static BdCreateOutcome Made(string id) => new(true, string.Empty, id);

    public static BdCreateOutcome Failure(string message) => new(false, message, string.Empty);

    /// <summary>The bead exists, but a write after it did not run.</summary>
    public static BdCreateOutcome MadeButNotStarted(string id, string message) => new(true, message, id);

    /// <summary>True when every write of the create ran, so the new bead is what the app meant.</summary>
    public bool Whole => Created && Message.Length == 0;
}
