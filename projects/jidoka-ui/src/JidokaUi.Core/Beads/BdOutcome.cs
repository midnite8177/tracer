namespace JidokaUi.Core.Beads;

/// <summary>The result of a read from bd: the beads it gave, or the reason it gave none.</summary>
/// <param name="Answered">True when bd ran and the app parsed its output.</param>
/// <param name="Message">Empty when bd answered; otherwise a message for the person.</param>
/// <param name="GaveUp">True when bd did not answer in time, so the app gave up on the read.</param>
public sealed record BdOutcome(bool Answered, string Message, IReadOnlyList<BeadRecord> Records, bool GaveUp)
{
    public static BdOutcome Answer(IReadOnlyList<BeadRecord> records) => new(true, string.Empty, records, false);

    public static BdOutcome Failure(string message) => new(false, message, [], false);

    public static BdOutcome Abandoned(string message) => new(false, message, [], true);
}
