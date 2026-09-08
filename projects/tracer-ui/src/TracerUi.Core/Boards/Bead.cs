using System.Globalization;
using TracerUi.Core.Beads;

namespace TracerUi.Core.Boards;

/// <summary>One bead of a project, with the field names of the installed bd already resolved.</summary>
/// <param name="Priority">The priority number, or null when the bead states none.</param>
/// <param name="ParentId">The id of the epic that holds this bead, or an empty string.</param>
/// <param name="Blockers">The ids of the beads that must close before this one, as its own edges name them.</param>
public sealed record Bead(
    string Id,
    string Title,
    string Type,
    long? Priority,
    string Assignee,
    IReadOnlyList<string> Labels,
    string ParentId,
    BeadProse Prose,
    IReadOnlyList<string> Blockers,
    string Status,
    string CloseReason)
{
    /// <summary>The label that marks a bead as one that waits on a person.</summary>
    public const string HumanLabel = "human";

    /// <summary>True when this bead states a priority of its own.</summary>
    public bool HasPriority => Priority is not null;

    /// <summary>
    /// A priority as text: the number alone, which the board draws and a part of the board filter
    /// names. The board and the filter bar read the same rule, so one press and one control name a
    /// priority the same way.
    /// </summary>
    public static string PriorityAsText(long priority) => priority.ToString(CultureInfo.InvariantCulture);

    /// <summary>The priority of this bead as text, or an empty string when it states none.</summary>
    public string PriorityText => Priority is { } priority ? PriorityAsText(priority) : string.Empty;

    public bool IsEpic => Type == "epic";

    public bool IsClosed => Status == StoredStatus.Closed;

    public bool NeedsYou => Labels.Contains(HumanLabel, StringComparer.OrdinalIgnoreCase);

    /// <summary>A close reason belongs to a closed bead, so an open bead never shows one.</summary>
    public bool HasCloseReason => IsClosed && CloseReason.Length > 0;

    // The edge types with which a version of bd states that an epic holds a bead.
    private static readonly string[] ParentEdgeTypes = ["parent-child", "parent"];

    // The edge type with which bd states that one bead must close before another.
    private const string BlocksEdgeType = "blocks";

    public static Bead From(BeadRecord record)
    {
        var edges = record.Edges(BeadFields.Candidates("dependencies"));
        return new Bead(
            record.Text(BeadFields.IdNames),
            record.Text(BeadFields.Candidates("title")),
            record.Text(BeadFields.Candidates("type")),
            record.NullableNumber(BeadFields.Candidates("priority")),
            record.Text(BeadFields.Candidates("assignee")),
            record.Strings(BeadFields.Candidates("labels")),
            EpicOf(record, edges),
            new BeadProse(
                record.Text(BeadFields.Candidates("description")),
                record.Text(BeadFields.Candidates("acceptance")),
                record.Text(BeadFields.Candidates("notes"))),
            TargetsOf(edges, BlocksEdgeType),
            record.Text(BeadFields.Candidates("status")),
            record.Text(BeadFields.Candidates("close-reason")));
    }

    // The epic that holds this bead. Some versions of bd name it in a field of its own, and others
    // state it only as a dependency edge.
    private static string EpicOf(BeadRecord record, IReadOnlyList<BeadEdge> edges)
    {
        var named = record.Text(BeadFields.Candidates("parent"));
        return named.Length > 0
            ? named
            : ParentEdgeTypes.SelectMany(type => TargetsOf(edges, type)).FirstOrDefault(string.Empty);
    }

    private static IReadOnlyList<string> TargetsOf(IReadOnlyList<BeadEdge> edges, string type) =>
        [.. edges
            .Where(edge => edge.Type == type && edge.TargetId.Length > 0)
            .Select(edge => edge.TargetId)];
}
