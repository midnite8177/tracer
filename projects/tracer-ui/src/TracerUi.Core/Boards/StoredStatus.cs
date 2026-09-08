using TracerUi.Core.Beads;

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

    /// <summary>The word of one stored status, the machine form that a write of the status carries.</summary>
    public static string Word(this StoredStatusWord status) => status switch
    {
        StoredStatusWord.Open => Open,
        StoredStatusWord.InProgress => InProgress,
        StoredStatusWord.Deferred => Deferred,
        StoredStatusWord.Closed => Closed,
        _ => throw new ArgumentOutOfRangeException(nameof(status), status, "This status has no word."),
    };

    /// <summary>The stored status that this word names, or none when it names none of the four.</summary>
    public static bool TryParse(string word, out StoredStatusWord status) =>
        EnumWord.TryParse(word, Word, out status);
}

/// <summary>
/// One of the four stored statuses that bd itself accepts on a write, so a write can carry no other.
/// </summary>
public enum StoredStatusWord
{
    Open,
    InProgress,
    Deferred,
    Closed,
}
