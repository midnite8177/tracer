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
/// What a press to edit opens: the entries of one field, how many of them the bead stands in, and
/// the box that makes an entry the field does not offer yet.
/// </summary>
/// <param name="Marks">How many entries of this picker the bead stands in.</param>
/// <param name="Choices">What the picker offers, in the order that it draws them.</param>
/// <param name="Addition">
/// The box at the foot that makes a value the entries do not hold, or none when the entries are the
/// whole field.
/// </param>
public sealed record FactPicker(
    FactMarks Marks,
    IReadOnlyList<FactChoice> Choices,
    FactAddition? Addition)
{
    /// <summary>A picker of a field that holds one value, and offers no value beyond its entries.</summary>
    public static FactPicker OfOneOf(IReadOnlyList<FactChoice> choices) =>
        new(FactMarks.TheOneItIsIn, choices, null);
}

/// <summary>
/// How many entries of one picker a bead stands in, which is what a mark on an entry means and how a
/// reader hears it: the one value of the field, or each of the several that the bead carries.
/// </summary>
public enum FactMarks
{
    /// <summary>The bead stands in one entry, thus a mark says which value the field holds.</summary>
    TheOneItIsIn,

    /// <summary>The bead carries any number of entries, thus each one is a mark that a press turns off.</summary>
    EachOneItCarries,
}
