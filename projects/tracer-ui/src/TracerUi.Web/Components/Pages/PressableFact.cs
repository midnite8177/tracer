using TracerUi.Core.Beads;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// One fact of the strip that a person presses to change: what it says, what a press of it opens,
/// and the actions of bd that a pick runs. The parts travel together, because they describe one
/// field.
/// </summary>
/// <param name="Name">The field, as the heading of the box prints it.</param>
/// <param name="HeadingId">The id of that heading, which the open picker names as its own label.</param>
/// <param name="Value">The value of the fact, as a person reads it.</param>
/// <param name="ValueClass">
/// The class that the value carries beside its own, which the stylesheet turns into the look of that
/// value: the quiet look of a fact the bead does not carry, or the color of a status. Empty when the
/// value reads as the text around it.
/// </param>
/// <param name="Page">
/// The address of the page that this value names, or empty when the value names none. The epic of a
/// bead is a bead of its own, so its box carries a link to it beside the press that changes it.
/// </param>
/// <param name="Verbs">
/// Every action of bd that an entry of the picker runs, so that a bd without one of them refuses
/// the press and names what it lacks, instead of offering an entry that cannot land.
/// </param>
/// <param name="Picker">What a press of this value opens.</param>
public sealed record PressableFact(
    string Name,
    string HeadingId,
    string Value,
    string ValueClass,
    string Page,
    IReadOnlyList<UiVerb> Verbs,
    FactPicker Picker);

/// <summary>
/// What a press to edit opens: the entries of one field, as a picker of one value or a picker of
/// several.
/// </summary>
public abstract record FactPicker
{
    // Closes the hierarchy, so a row that handles these two kinds handles every picker.
    private FactPicker()
    {
    }

    /// <summary>
    /// The picker of a field that holds one value. A pick writes at once, or asks its question
    /// first, and closes the picker. It offers no value beyond its entries.
    /// </summary>
    /// <param name="Choices">What the picker offers, in the order that it draws them.</param>
    public sealed record OfOneOf(IReadOnlyList<FactChoice> Choices) : FactPicker;

    /// <summary>
    /// The picker of a field that a bead carries several values of. A press of an entry writes
    /// nothing and makes an unsaved tick, and Save sends every unsaved tick as one change, because
    /// several ticks of one field are one change.
    /// </summary>
    /// <param name="Entries">What the picker offers, in the order that it draws them.</param>
    /// <param name="Addition">
    /// The box at the foot that ticks a typed word, on its entry when the project uses it, or on a new
    /// entry at the foot.
    /// </param>
    /// <param name="Save">The write that Save runs with the change that the unsaved ticks make.</param>
    public sealed record OfSeveral(
        IReadOnlyList<FactTick> Entries,
        FactAddition Addition,
        Func<FactChange, Task<BdWriteOutcome>> Save) : FactPicker;
}

/// <summary>
/// One entry of a picker of several: a label that the project uses, and the spelling of it that the
/// bead carries. The two can differ in case, and bd holds the label as the bead spells it.
/// </summary>
/// <param name="Label">The spelling that the entry prints and that an add sends.</param>
/// <param name="Carried">
/// The spelling that the bead carries, which a removal sends, or null when the bead lacks the label.
/// </param>
public sealed record FactTick(BeadLabel Label, BeadLabel? Carried)
{
    public string Text => Label.Word;

    public bool Marked => Carried is not null;
}

/// <summary>What one Save sends: the labels to put on, and the labels to take off as the bead spells them.</summary>
public sealed record FactChange(IReadOnlyList<BeadLabel> Adds, IReadOnlyList<BeadLabel> Removes);
