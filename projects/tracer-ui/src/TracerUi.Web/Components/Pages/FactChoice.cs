using TracerUi.Core.Beads;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// One entry of a picker of one value: the words that a person reads, and the write that a pick of it
/// runs. The entry carries its own write, so nothing turns a value into text and reads it back again.
/// An entry whose write needs words from a person carries the question that a pick of it opens.
/// </summary>
/// <param name="Text">What the entry says to a person.</param>
/// <param name="Marked">
/// True when the bead stands in this entry now. The picker marks it, because the value of a row does
/// not always print the entry that it stands for.
/// </param>
/// <param name="Question">The question that a pick opens, or none when the pick writes at once.</param>
/// <param name="Write">The write that a pick runs, with the answer to that question or an empty string.</param>
public sealed record FactChoice(
    string Text,
    bool Marked,
    FactQuestion? Question,
    Func<string, Task<BdWriteOutcome>> Write)
{
    /// <summary>An entry whose pick writes at once, because bd needs nothing from the person.</summary>
    public static FactChoice ThatWrites(string text, bool marked, Func<Task<BdWriteOutcome>> write) =>
        new(text, marked, null, _ => write());
}

/// <summary>
/// What one entry of a fact picker asks before it writes. It is the guard on a write that must not
/// leave a hole in the history of a bead: the entry writes nothing until the person answers, so the
/// picker that offers closed is also the place that asks why.
/// </summary>
/// <param name="Prompt">What the question asks for, which names the field to a reader.</param>
/// <param name="Press">The words on the button that runs the write.</param>
public sealed record FactQuestion(string Prompt, string Press);

/// <summary>
/// The box at the foot of a fact picker that ticks a typed word, on its entry when the project uses
/// it, or on a new entry at the foot. A field whose entries are the vocabulary of a project needs it,
/// because a list of what the project already says traps the person who has a new word for it. The
/// box writes nothing. What it takes becomes an unsaved add, and Save sends it with the rest.
/// </summary>
/// <param name="Question">What the box asks for, and the words on the button beside it.</param>
/// <param name="Check">
/// What the box makes of the text that the person typed, which it gets as typed and untrimmed. It
/// refuses what Save cannot send.
/// </param>
public sealed record FactAddition(FactQuestion Question, Func<string, TypedLabel> Check);

/// <summary>What the box at the foot of a picker of several makes of a typed word.</summary>
public abstract record TypedLabel
{
    // Closes the hierarchy, so a box that handles these two kinds handles every answer.
    private TypedLabel()
    {
    }

    /// <summary>A word that the box takes, as the spelling that Save will send.</summary>
    public sealed record ToTick(BeadLabel Label) : TypedLabel;

    /// <summary>A word that the box refuses, and what the person reads about it.</summary>
    public sealed record Refused(string Reason) : TypedLabel;
}
