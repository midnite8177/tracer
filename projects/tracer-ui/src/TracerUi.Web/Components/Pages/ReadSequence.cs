namespace TracerUi.Web.Components.Pages;

/// <summary>What began a read of the detail page.</summary>
public enum ReadCause
{
    /// <summary>
    /// The person: the first read of the bead, or the re-read that one of their writes caused.
    /// </summary>
    ThePerson,

    /// <summary>The project watcher saw the project change, so no person waits on the read.</summary>
    TheProjectWatcher,
}

/// <summary>
/// The order of the reads that the detail page begins. A person writes while the project watcher
/// reads, so two reads of one bead run at once and bd answers them in either order. This answers
/// which answer may land on the page and which read carries the re-read mark.
/// </summary>
public sealed class ReadSequence
{
    private int begun;
    private int theLatestLanded;
    private int theReadThatOwnsTheMark;

    /// <summary>True while the latest read of the person runs over what the page already shows.</summary>
    public bool Rereading { get; private set; }

    /// <summary>
    /// Begins a read and gives its place in the order. A read of the person takes the re-read mark
    /// from every read before it. A read of the project watcher carries no mark and takes none.
    /// </summary>
    /// <param name="cause">What began the read.</param>
    /// <param name="keepsWhatIsOnTheScreen">
    /// True when the page shows a bead through the read. A first read keeps nothing, so it carries
    /// no mark.
    /// </param>
    public int Begin(ReadCause cause, bool keepsWhatIsOnTheScreen)
    {
        var read = ++begun;
        if (cause is ReadCause.ThePerson)
        {
            theReadThatOwnsTheMark = read;
            Rereading = keepsWhatIsOnTheScreen;
        }

        return read;
    }

    /// <summary>
    /// Ends a read once bd answered it or the app stopped waiting. The mark goes with the read that
    /// owns it, and with no other.
    /// </summary>
    public void End(int read)
    {
        // A check of the latest read instead would take the mark off when a read of the project
        // watcher that began later ends first, while the re-read of the person still runs.
        if (read == theReadThatOwnsTheMark)
        {
            Rereading = false;
        }
    }

    /// <summary>
    /// Whether the answer of this read may land on the page. It may not once the answer of a read
    /// that began after it has landed.
    /// </summary>
    public bool CanLand(int read) => read >= theLatestLanded;

    /// <summary>Records that the answer of this read is the one on the page.</summary>
    public void Land(int read) => theLatestLanded = read;

    /// <summary>Whether no read began after this one.</summary>
    public bool IsTheLatest(int read) => read == begun;
}
