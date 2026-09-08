namespace TracerUi.Core.Boards;

/// <summary>
/// The status words that bd itself keeps on a bead. The resolved status of a row is built from one
/// of these, together with the labels of the bead and what bd says is ready and blocked.
/// </summary>
public static class StoredStatus
{
    public const string Open = "open";

    public const string InProgress = "in_progress";

    public const string Deferred = "deferred";

    public const string Closed = "closed";

    /// <summary>The four, in the order that a person walks a bead through them.</summary>
    public static IReadOnlyList<string> All { get; } = [Open, InProgress, Deferred, Closed];

    /// <summary>
    /// One stored status as a person reads it, where bd writes it as one machine word. Every control
    /// that offers a status reads this, so no two of them word the same status differently.
    /// </summary>
    public static string InWords(string status) => status.Replace('_', ' ');
}
