using System.Globalization;
using TracerUi.Core.Beads;

namespace TracerUi.Core.Boards;

/// <summary>One write that an action of the action bar makes to each bead of the selection.</summary>
public enum BulkVerb
{
    AddALabel,
    RemoveALabel,
    CloseWithAReason,
    Defer,
    MoveIntoAnEpic,
    SetThePriority,
    SetTheType,
}

/// <summary>What a person gives the action bar before an action of a category can run.</summary>
public enum BulkValue
{
    Nothing,
    ALabel,
    AReason,
    AnEpic,
    APriority,
    AType,
}

/// <summary>
/// What one verb is called, what it needs from the installed bd, how the plan says it, and how the
/// adapter does it. One shape per verb holds all four, so a new verb has one home and not five.
/// </summary>
public sealed record BulkVerbShape(
    string Name,
    UiVerb Write,
    bool NeedsAValue,
    Func<BulkPlan, string> Sentence,
    Func<BdAdapter, BeadAddress, BulkAction, BulkStep, Task<BdWriteOutcome>> Apply);

/// <summary>
/// One verb category of the action bar. A category names one verb, except the label category,
/// which names the two that a person reads as one choice.
/// </summary>
public sealed record BulkCategory(string Name, BulkValue Needs, IReadOnlyList<BulkVerb> Verbs)
{
    public static BulkCategory Label { get; } =
        new("Add or remove a label", BulkValue.ALabel, [BulkVerb.AddALabel, BulkVerb.RemoveALabel]);

    public static BulkCategory Close { get; } =
        new("Close with a reason", BulkValue.AReason, [BulkVerb.CloseWithAReason]);

    public static BulkCategory Defer { get; } =
        new("Defer", BulkValue.Nothing, [BulkVerb.Defer]);

    public static BulkCategory Epic { get; } =
        new("Move into an epic", BulkValue.AnEpic, [BulkVerb.MoveIntoAnEpic]);

    public static BulkCategory Priority { get; } =
        new("Set the priority", BulkValue.APriority, [BulkVerb.SetThePriority]);

    public static BulkCategory Type { get; } =
        new("Set the type", BulkValue.AType, [BulkVerb.SetTheType]);

    /// <summary>The six categories, in the order that the action bar shows them.</summary>
    public static IReadOnlyList<BulkCategory> All { get; } = [Label, Close, Defer, Epic, Priority, Type];

    /// <summary>The category of this name, or the first one when no category carries it.</summary>
    public static BulkCategory Named(string name) =>
        All.FirstOrDefault(category => category.Name == name) ?? Label;

    /// <summary>
    /// The write that this category needs. Both label verbs need the one label write, so the first
    /// verb answers for the category.
    /// </summary>
    public UiVerb Write => BulkVerbs.Of(Verbs[0]).Write;
}

/// <summary>Every verb of the action bar, and what each one is.</summary>
public static class BulkVerbs
{
    private static readonly IReadOnlyDictionary<BulkVerb, BulkVerbShape> Shapes =
        new Dictionary<BulkVerb, BulkVerbShape>
        {
            [BulkVerb.AddALabel] = new(
                "Add a label",
                UiVerbs.LabelABead,
                true,
                plan => $"Add the label {plan.Action.Value} to {plan.Beads}.",
                (bd, bead, action, _) => bd.AddLabelAsync(bead, action.Value)),
            [BulkVerb.RemoveALabel] = new(
                "Remove a label",
                UiVerbs.LabelABead,
                true,
                plan => $"Remove the label {plan.Action.Value} from {plan.Beads}.",
                (bd, bead, action, _) => bd.RemoveLabelAsync(bead, action.Value)),
            [BulkVerb.CloseWithAReason] = new(
                "Close with a reason",
                UiVerbs.CloseWithAReason,
                false,
                plan => $"Close {plan.Beads}. {plan.OwnReasons}",
                (bd, bead, _, step) => bd.CloseAsync(bead, step.Reason)),
            [BulkVerb.Defer] = new(
                "Defer",
                UiVerbs.DeferABead,
                false,
                plan => $"Defer {plan.Beads}.",
                (bd, bead, _, _) => bd.DeferAsync(bead)),
            [BulkVerb.MoveIntoAnEpic] = new(
                "Move into an epic",
                UiVerbs.MoveIntoAnEpic,
                true,
                plan => $"Move {plan.Beads} into {plan.Action.Value}.",
                (bd, bead, action, _) => bd.SetParentAsync(bead, action.Value)),
            [BulkVerb.SetThePriority] = new(
                "Set the priority",
                UiVerbs.SetThePriority,
                true,
                plan => $"Set the priority of {plan.Beads} to p{plan.Action.Value}.",
                (bd, bead, action, _) => SetThePriorityAsync(bd, bead, action.Value)),
            [BulkVerb.SetTheType] = new(
                "Set the type",
                UiVerbs.SetTheType,
                true,
                plan => $"Set the type of {plan.Beads} to {plan.Action.Value}.",
                (bd, bead, action, _) => bd.SetTypeAsync(bead, action.Value)),
        };

    /// <summary>
    /// Every member of <see cref="BulkVerb"/> has an entry, so a verb added to the enum and not to
    /// the table throws here rather than reaching the action bar half-built.
    /// </summary>
    public static BulkVerbShape Of(BulkVerb verb) => Shapes[verb];

    // Sets the priority that the action states. bd takes a number, so a value that is not one is a
    // message for the person and not a write.
    private static Task<BdWriteOutcome> SetThePriorityAsync(BdAdapter bd, BeadAddress bead, string value) =>
        long.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var priority)
            ? bd.SetPriorityAsync(bead, priority)
            : Task.FromResult(BdWriteOutcome.Failure($"{value} is not a priority number."));
}

/// <summary>
/// One action of the action bar: the verb, and the one value that the verb needs. A defer needs no
/// value, and a close takes its reason from the plan, because the person edits the reason of a bead
/// on its own.
/// </summary>
public sealed record BulkAction(BulkVerb Verb, string Value)
{
    public static BulkAction AddTheLabel(string label) => new(BulkVerb.AddALabel, label);

    public static BulkAction RemoveTheLabel(string label) => new(BulkVerb.RemoveALabel, label);

    public static BulkAction CloseThem(string reason) => new(BulkVerb.CloseWithAReason, reason);

    public static BulkAction DeferThem() => new(BulkVerb.Defer, string.Empty);

    public static BulkAction MoveIntoTheEpic(string epicId) => new(BulkVerb.MoveIntoAnEpic, epicId);

    public static BulkAction SetThePriority(long priority) =>
        new(BulkVerb.SetThePriority, priority.ToString(CultureInfo.InvariantCulture));

    public static BulkAction SetTheType(string type) => new(BulkVerb.SetTheType, type);

    public BulkVerbShape Shape => BulkVerbs.Of(Verb);
}
