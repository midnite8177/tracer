namespace JidokaUi.Core.Beads;

/// <summary>
/// The result of a read from bd. It is one of three cases, so that no result is both an answer and a
/// give-up: bd gave the beads, bd failed, or the app stopped waiting on bd.
/// </summary>
public abstract record BdOutcome
{
    private BdOutcome()
    {
    }

    /// <summary>True when bd ran and the app parsed its output.</summary>
    public bool Answered => this is Given;

    /// <summary>True when bd did not answer in time, so the app gave up on the read.</summary>
    public bool GaveUp => this is Abandoned;

    /// <summary>The beads that bd gave, or none when bd gave none.</summary>
    public IReadOnlyList<BeadRecord> Records => this is Given given ? given.Beads : [];

    /// <summary>Empty when bd answered; otherwise a message for the person.</summary>
    public string Message => this switch
    {
        Failed failed => failed.Reason,
        Abandoned abandoned => abandoned.Reason,
        _ => string.Empty,
    };

    /// <summary>bd ran and the app parsed its output.</summary>
    public sealed record Given(IReadOnlyList<BeadRecord> Beads) : BdOutcome;

    /// <summary>bd did not run, failed, or printed something the app could not read.</summary>
    public sealed record Failed(string Reason) : BdOutcome;

    /// <summary>bd did not answer in time, so the app stopped the read.</summary>
    public sealed record Abandoned(string Reason) : BdOutcome;
}
