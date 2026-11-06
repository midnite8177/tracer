namespace JidokaUi.Core.Beads;

/// <summary>
/// The result of a write to bd. It is one of three cases, so that no result is both a write and a
/// give-up: bd made the change, it did not, or the app stopped waiting on bd.
/// </summary>
public abstract record BdWriteOutcome
{
    private BdWriteOutcome()
    {
    }

    /// <summary>True when bd made the change.</summary>
    public bool Wrote => this is Written;

    /// <summary>True when the app stopped waiting on bd, so this write may still have landed.</summary>
    public bool GaveUp => this is Abandoned;

    /// <summary>Empty when bd wrote; otherwise a message for the person.</summary>
    public string Message => this switch
    {
        Failed failed => failed.Reason,
        Abandoned abandoned => abandoned.Reason,
        _ => string.Empty,
    };

    /// <summary>A write that ended before it ran, as an already finished task, for a caller that refuses it.</summary>
    public static Task<BdWriteOutcome> FailedTask(string reason) =>
        Task.FromResult<BdWriteOutcome>(new Failed(reason));

    /// <summary>
    /// The same kind of ending in other words: a failure stays a failure and a give-up stays a give-up,
    /// and a write that bd made has no words to change.
    /// </summary>
    public BdWriteOutcome WithMessage(string message) => this switch
    {
        Failed => new Failed(message),
        Abandoned => new Abandoned(message),
        _ => this,
    };

    /// <summary>bd made the change.</summary>
    public sealed record Written : BdWriteOutcome;

    /// <summary>bd did not make the change, or the app did not start bd.</summary>
    public sealed record Failed(string Reason) : BdWriteOutcome;

    /// <summary>The app stopped waiting on bd, which the app does not stop, so the write may still land.</summary>
    public sealed record Abandoned(string Reason) : BdWriteOutcome;
}
