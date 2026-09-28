using TracerUi.Core.Beads;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// The unsaved ticks of one open picker of several, the entries that its box added, and what the
/// box said about the last word it refused. It writes nothing, and a close of the picker forgets it
/// all.
/// </summary>
public sealed class UnsavedTicks
{
    private readonly Dictionary<string, UnsavedTick> ticks = new(StringComparer.Ordinal);
    private readonly List<FactTick> typedEntries = [];

    private enum UnsavedTick
    {
        Addition,
        Removal,
    }

    /// <summary>
    /// Why the box refused the last word typed into it. Null once the box takes a word or a press
    /// ticks an entry.
    /// </summary>
    public string? WhyTheBoxRefused { get; private set; }

    /// <summary>
    /// The entries of the picker, then the entries that the box added, in the order they were typed.
    /// </summary>
    public IEnumerable<FactTick> TheEntriesOf(FactPicker.OfSeveral several) => several.Entries.Concat(typedEntries);

    public EntryState TheStateOf(FactTick entry) => (entry.Marked, ticks.ContainsKey(entry.Text)) switch
    {
        (true, false) => EntryState.Carried,
        (false, false) => EntryState.NotCarried,
        (false, true) => EntryState.ToAdd,
        (true, true) => EntryState.ToRemove,
    };

    public IReadOnlyList<FactTick> UnsavedIn(FactPicker.OfSeveral several) =>
        [.. TheEntriesOf(several).Where(entry => ticks.ContainsKey(entry.Text))];

    /// <summary>A second press of an entry takes its unsaved tick back.</summary>
    public void Tick(FactTick entry)
    {
        WhyTheBoxRefused = null;
        if (!ticks.Remove(entry.Text))
        {
            ticks.Add(entry.Text, ThePressOf(entry));
        }
    }

    /// <summary>
    /// Puts a plus on the word typed into the box at the foot, on the entry of that label, or on a new
    /// entry when the picker has none. A refused word keeps the reason of the box instead.
    /// </summary>
    /// <returns>True when the box took the word, so the box can empty.</returns>
    public bool Add(FactPicker.OfSeveral several, string typed)
    {
        WhyTheBoxRefused = null;
        switch (several.Addition.Check(typed))
        {
            case TypedLabel.ToTick(var label):
                return TickTheTypedLabel(several, label);
            case TypedLabel.Refused refused:
                WhyTheBoxRefused = refused.Reason;
                break;
        }

        return false;
    }

    /// <summary>
    /// Keeps the ticks that a re-read left to change. A typed entry whose label the re-read now lists
    /// gives way to the listed entry, which takes its plus when the bead still lacks the label.
    /// </summary>
    public void SettleAfterAReRead(FactPicker picker)
    {
        IReadOnlyList<FactTick> entries = picker is FactPicker.OfSeveral several ? several.Entries : [];
        MoveThePlusesOfTypedEntriesThatAReReadListed(entries);
        ForgetTheTicksThatAReReadSettled(entries.Concat(typedEntries));
    }

    public void Forget()
    {
        WhyTheBoxRefused = null;
        ticks.Clear();
        typedEntries.Clear();
    }

    private static UnsavedTick ThePressOf(FactTick entry) => entry.Marked ? UnsavedTick.Removal : UnsavedTick.Addition;

    // The box never ticks a label that the bead carries, because a plus there would change nothing.
    private bool TickTheTypedLabel(FactPicker.OfSeveral several, BeadLabel label)
    {
        var entry = TheEntryOfTheTypedLabel(several, label);
        if (entry.Marked)
        {
            return false;
        }

        ticks[entry.Text] = UnsavedTick.Addition;
        return true;
    }

    private FactTick TheEntryOfTheTypedLabel(FactPicker.OfSeveral several, BeadLabel label)
    {
        if (TheEntriesOf(several).FirstOrDefault(entry => label.ReadsTheSameAs(entry.Text)) is { } entry)
        {
            return entry;
        }

        var typed = new FactTick(label, null);
        typedEntries.Add(typed);
        return typed;
    }

    private void MoveThePlusesOfTypedEntriesThatAReReadListed(IReadOnlyList<FactTick> entries)
    {
        foreach (var typed in typedEntries.ToList())
        {
            if (entries.FirstOrDefault(entry => typed.Label.ReadsTheSameAs(entry.Text)) is not { } listed)
            {
                continue;
            }

            typedEntries.Remove(typed);
            if (ticks.Remove(typed.Text) && !listed.Marked)
            {
                ticks[listed.Text] = UnsavedTick.Addition;
            }
        }
    }

    // Every read of the entries trusts that each stored tick still changes something. That holds
    // because each writer stores a change: a press stores the opposite of what the bead carries, and
    // the box and a re-read put a plus only on an entry that the bead lacks. This drops every tick
    // that a re-read settled.
    private void ForgetTheTicksThatAReReadSettled(IEnumerable<FactTick> entries)
    {
        var stillChanging = entries
            .Where(entry => ticks.TryGetValue(entry.Text, out var tick) && tick == ThePressOf(entry))
            .Select(entry => entry.Text)
            .ToHashSet(StringComparer.Ordinal);
        foreach (var word in ticks.Keys.Where(word => !stillChanging.Contains(word)).ToList())
        {
            ticks.Remove(word);
        }
    }
}

/// <summary>
/// What one entry of a picker of several shows: whether the bead carries it, and what Save will do
/// to it.
/// </summary>
public enum EntryState
{
    Carried,
    NotCarried,
    ToAdd,
    ToRemove,
}
