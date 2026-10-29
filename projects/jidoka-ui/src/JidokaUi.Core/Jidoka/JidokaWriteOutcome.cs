namespace JidokaUi.Core.Jidoka;

/// <summary>
/// The result of a script of jidoka that writes. It is one of three cases, so that no result is both
/// a write and a give-up: the script wrote, it did not, or the app stopped waiting on it.
/// </summary>
public abstract record JidokaWriteOutcome
{
    private JidokaWriteOutcome()
    {
    }

    /// <summary>True when the script exited with success.</summary>
    public bool Wrote => this is Written;

    /// <summary>True when the app stopped waiting on the script, so it may still finish.</summary>
    public bool GaveUp => this is Abandoned;

    /// <summary>Empty when the script wrote; otherwise what the script said, for the person.</summary>
    public string Message => this switch
    {
        Failed failed => failed.Reason,
        Abandoned abandoned => abandoned.Reason,
        _ => string.Empty,
    };

    /// <summary>What the script printed on success, such as the commit that a merge landed.</summary>
    public string Output => this is Written written ? written.Printed : string.Empty;

    /// <summary>The script exited with success.</summary>
    public sealed record Written(string Printed) : JidokaWriteOutcome;

    /// <summary>The script did not write, or the app could not start it.</summary>
    public sealed record Failed(string Reason) : JidokaWriteOutcome;

    /// <summary>The app stopped waiting on the script, which the app cannot stop.</summary>
    public sealed record Abandoned(string Reason) : JidokaWriteOutcome;
}
