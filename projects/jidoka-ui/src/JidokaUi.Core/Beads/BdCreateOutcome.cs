namespace JidokaUi.Core.Beads;

/// <summary>
/// The result of a create. It is one of four cases: the bead exists and every write of the create
/// ran, the bead exists but a write after it did not run, bd made none, or the app stopped waiting
/// on bd. A create can take more than one write, so a bead can exist and the message still say what
/// went wrong after bd made it. The message is what the person reads, whatever the app made.
/// </summary>
public abstract record BdCreateOutcome
{
    private BdCreateOutcome()
    {
    }

    /// <summary>True when the bead exists.</summary>
    public bool Created => this is Made or MadeButNotStarted;

    /// <summary>True when every write of the create ran, so the new bead is what the app meant.</summary>
    public bool Whole => this is Made;

    /// <summary>True when the app stopped waiting on bd, so this create may still have landed.</summary>
    public bool GaveUp => this is Abandoned;

    /// <summary>The id that bd gave the new bead, or an empty string when bd made none.</summary>
    public string Id => this switch
    {
        Made made => made.BeadId,
        MadeButNotStarted partial => partial.BeadId,
        _ => string.Empty,
    };

    /// <summary>Empty when every write of the create ran; otherwise a message for the person.</summary>
    public string Message => this switch
    {
        MadeButNotStarted partial => partial.Reason,
        Failed failed => failed.Reason,
        Abandoned abandoned => abandoned.Reason,
        _ => string.Empty,
    };

    /// <summary>The bead exists and every write of the create ran.</summary>
    public sealed record Made(string BeadId) : BdCreateOutcome;

    /// <summary>The bead exists, but a write after it did not run.</summary>
    public sealed record MadeButNotStarted(string BeadId, string Reason) : BdCreateOutcome;

    /// <summary>bd made no bead.</summary>
    public sealed record Failed(string Reason) : BdCreateOutcome;

    /// <summary>The app stopped waiting on bd, so this create may still have landed.</summary>
    public sealed record Abandoned(string Reason) : BdCreateOutcome;
}
