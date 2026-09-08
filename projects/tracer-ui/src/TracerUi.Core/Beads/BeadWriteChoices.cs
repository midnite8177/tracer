using TracerUi.Core.Boards;

namespace TracerUi.Core.Beads;

/// <summary>
/// The choices that a write offers for the fields a person sets, on one bead or on a selection.
/// </summary>
public static class BeadWriteChoices
{
    /// <summary>
    /// The four stored statuses, because a person asks one question about the state of a bead where
    /// bd gives three verbs.
    /// </summary>
    public static IReadOnlyList<string> Statuses { get; } = StoredStatus.All;

    /// <summary>
    /// The types that bd itself ships. A project can configure more of them, and this list does not
    /// know those, so a type that this bd refuses comes back as a message from bd and not as an
    /// error of the app.
    /// </summary>
    public static IReadOnlyList<string> Types { get; } =
        [.. Enum.GetValues<BeadTypeWord>().Select(BeadType.Word)];

    /// <summary>
    /// The types that quick create offers. It leaves out the epic, because an epic takes a second
    /// write that sets it to in progress, and a type control here would make one that stayed open.
    /// The epic has an action of its own beside quick create.
    /// </summary>
    public static IReadOnlyList<string> QuickCreateTypes { get; } =
        [.. Types.Where(type => type != EpicType)];

    /// <summary>The type that bd gives a bead which holds other beads.</summary>
    public const string EpicType = BeadType.Epic;

    /// <summary>
    /// Every surface that offers a quick create says this, so the promise reads the same wherever a
    /// person captures a bead.
    /// </summary>
    public const string WhatAQuickCreateMakes =
        "A bead from here carries no description, so the board marks it as one with no demo line.";

    /// <summary>The priority numbers that bd takes, from the most urgent to the least.</summary>
    public static IReadOnlyList<long> Priorities { get; } = [0, 1, 2, 3, 4];
}
