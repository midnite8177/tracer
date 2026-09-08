namespace TracerUi.Core.Boards;

/// <summary>
/// Which beads of a backlog the board keeps. Every part that carries a value narrows the board, and
/// the parts combine. An empty part states nothing and keeps every bead. The filter also holds what
/// the board shows beyond the live beads, because that choice narrows the board in the same way.
/// </summary>
/// <param name="Status">The stored status that a bead must have. It supersedes the two show parts.</param>
/// <param name="Type">The type that a bead must have.</param>
/// <param name="Priority">The priority number, as text, that a bead must have.</param>
/// <param name="Label">A label that a bead must carry.</param>
/// <param name="Epic">The id of an epic that must hold a bead, at any depth, or be the bead.</param>
/// <param name="Text">Text that the title, the description or a label of a bead must hold.</param>
/// <param name="RequiresHumanLabel">True when the board keeps only the beads that wait on a person.</param>
/// <param name="RequiresNoDemoLine">True when the board keeps only the beads that have no Demo line.</param>
/// <param name="ShowDeferred">True when the board shows the deferred beads.</param>
/// <param name="ShowClosed">True when the board shows the closed beads.</param>
public sealed record BoardFilter(
    string Status,
    string Type,
    string Priority,
    string Label,
    string Epic,
    string Text,
    bool RequiresHumanLabel,
    bool RequiresNoDemoLine,
    bool ShowDeferred,
    bool ShowClosed)
{
    /// <summary>
    /// The filter that keeps every live bead. It is what the board shows before a person narrows it:
    /// the open and the in-progress beads, which are the backlog a person works.
    /// </summary>
    public static BoardFilter Everything { get; } = new(
        Status: string.Empty,
        Type: string.Empty,
        Priority: string.Empty,
        Label: string.Empty,
        Epic: string.Empty,
        Text: string.Empty,
        RequiresHumanLabel: false,
        RequiresNoDemoLine: false,
        ShowDeferred: false,
        ShowClosed: false);

    /// <summary>The beads that wait on a person: the ones that carry the human label.</summary>
    public static BoardFilter NeedsYou { get; } = Everything with { RequiresHumanLabel = true };

    /// <summary>The beads that no session can implement yet, because they state no Demo line.</summary>
    public static BoardFilter NoDemoLine { get; } = Everything with { RequiresNoDemoLine = true };

    /// <summary>
    /// The filter after a filter press on the type of a row. The press adds the type to the filter
    /// that is already set, so the parts a person chose before it stay.
    /// </summary>
    public BoardFilter AfterAPressOnType(string type) => this with { Type = PartAfterAPress(Type, type) };

    /// <summary>The filter after a filter press on the priority of a row.</summary>
    public BoardFilter AfterAPressOnPriority(string priority) =>
        this with { Priority = PartAfterAPress(Priority, priority) };

    /// <summary>The filter after a filter press on one label of a row.</summary>
    public BoardFilter AfterAPressOnLabel(string label) =>
        this with { Label = PartAfterAPress(Label, label) };

    /// <summary>
    /// The filter after a filter press on the marker of a row that states no Demo line. Only that
    /// marker presses, because the filter asks for the beads with no Demo line and for no other set.
    /// </summary>
    public BoardFilter AfterAPressOnTheNoDemoLineMarker() =>
        this with { RequiresNoDemoLine = !RequiresNoDemoLine };

    // What one part of the filter holds after a press on a row named a value for it. A press on the
    // value that the part already holds clears the part, so the same press that set it takes it off
    // again and a person needs no trip to the filter bar.
    private static string PartAfterAPress(string part, string pressed) =>
        string.Equals(part, pressed, StringComparison.OrdinalIgnoreCase) ? string.Empty : pressed;

    /// <summary>
    /// True when the board shows a bead in this stored status. A named status supersedes the two
    /// show parts, so a person who asks for the closed beads gets them without a second click.
    /// </summary>
    public bool Shows(string status) => Status.Length > 0 ? status == Status : ShowsByDefault(status);

    /// <summary>
    /// True when this bead passes every part of the filter. The epics above the bead run from the
    /// epic that holds it out to the outermost one, so that a filter on an epic keeps its whole tree.
    /// </summary>
    public bool Matches(Bead bead, IReadOnlyList<string> epicsAbove) =>
        MatchesType(bead)
        && MatchesPriority(bead)
        && MatchesLabel(bead)
        && MatchesEpic(bead, epicsAbove)
        && MatchesText(bead)
        && MatchesHumanLabel(bead)
        && MatchesDemoLine(bead);

    private bool ShowsByDefault(string status) => status switch
    {
        StoredStatus.Open => true,
        StoredStatus.InProgress => true,
        StoredStatus.Deferred => ShowDeferred,
        StoredStatus.Closed => ShowClosed,
        _ => false,
    };

    private bool MatchesType(Bead bead) =>
        Type.Length == 0 || string.Equals(bead.Type, Type, StringComparison.OrdinalIgnoreCase);

    // True when this bead carries the priority that the part names. The part holds the number as
    // text, because that is what the address of the board carries.
    private bool MatchesPriority(Bead bead) =>
        Priority.Length == 0 || string.Equals(Priority, bead.PriorityText, StringComparison.Ordinal);

    private bool MatchesLabel(Bead bead) =>
        Label.Length == 0 || bead.Labels.Contains(Label, StringComparer.OrdinalIgnoreCase);

    // True when this bead is in the tree that the epic part names. The epic itself is in its own
    // tree, so a filter on an epic keeps the epic, and an epic that holds no bead stays visible.
    private bool MatchesEpic(Bead bead, IReadOnlyList<string> epicsAbove) =>
        Epic.Length == 0
        || string.Equals(bead.Id, Epic, StringComparison.Ordinal)
        || epicsAbove.Contains(Epic, StringComparer.Ordinal);

    private bool MatchesText(Bead bead)
    {
        var text = Text.Trim();
        if (text.Length == 0)
        {
            return true;
        }

        return Holds(bead.Title, text)
            || Holds(bead.Prose.Description, text)
            || bead.Labels.Any(label => Holds(label, text));
    }

    private static bool Holds(string field, string text) =>
        field.Contains(text, StringComparison.OrdinalIgnoreCase);

    private bool MatchesHumanLabel(Bead bead) => !RequiresHumanLabel || bead.NeedsYou;

    private bool MatchesDemoLine(Bead bead) => !RequiresNoDemoLine || !bead.Prose.HasDemoLine;
}
