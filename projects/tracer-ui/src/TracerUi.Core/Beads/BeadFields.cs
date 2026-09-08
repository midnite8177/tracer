namespace TracerUi.Core.Beads;

/// <summary>One field of a bead that the UI reads.</summary>
/// <param name="Key">How the app names this field. It never changes.</param>
/// <param name="Label">How the doctor page names this field to a person.</param>
/// <param name="Candidates">The JSON names that a version of bd can give the field, in the order to try.</param>
public sealed record BeadField(string Key, string Label, IReadOnlyList<string> Candidates);

/// <summary>
/// The fields of a bead that the UI reads. The probe tries the candidate names of each field
/// in order, and it keeps the first one that a real bead shows.
/// </summary>
public static class BeadFields
{
    public static IReadOnlyList<BeadField> All { get; } =
    [
        new("id", "Id", ["id", "issue_id"]),
        new("title", "Title", ["title"]),
        new("status", "Status", ["status"]),
        new("type", "Type", ["issue_type", "type"]),
        new("priority", "Priority", ["priority"]),
        new("assignee", "Assignee", ["assignee", "owner"]),
        new("labels", "Labels", ["labels"]),
        new("parent", "Parent", ["parent", "parent_id"]),
        new("description", "Description", ["description"]),
        new("acceptance", "Acceptance criteria", ["acceptance_criteria", "acceptance"]),
        new("notes", "Notes", ["notes"]),
        new("dependencies", "Dependencies", ["dependencies", "deps"]),
        new("close-reason", "Close reason", ["close_reason", "closed_reason", "reason"]),
        new("deferred-until", "Deferred until", ["defer_until", "deferred_until"]),
    ];

    private static readonly Dictionary<string, BeadField> ByKey =
        All.ToDictionary(field => field.Key, StringComparer.Ordinal);

    /// <summary>The names that a version of bd can give one field, in the order to try them.</summary>
    public static IReadOnlyList<string> Candidates(string key) => ByKey[key].Candidates;

    /// <summary>The names that a version of bd can give the id of a bead.</summary>
    public static IReadOnlyList<string> IdNames => Candidates("id");

    /// <summary>
    /// The fields of one comment that the UI reads. bd keeps the comments of a bead behind its own
    /// command, so no bead in a list ever carries them.
    /// </summary>
    public static IReadOnlyList<BeadField> OfAComment { get; } =
    [
        new("text", "Text", ["text", "body", "comment"]),
        new("author", "Author", ["author", "created_by", "actor"]),
        new("created", "Created", ["created_at", "created", "timestamp"]),
    ];

    /// <summary>
    /// The fields of one dependency edge that the UI reads. One version of bd states the far end in
    /// a field of its own; another prints the whole bead there, where its own id names it.
    /// </summary>
    public static IReadOnlyList<BeadField> OfAnEdge { get; } =
    [
        new("type", "Type", ["dependency_type", "type"]),
        new("target", "Depends on", ["depends_on_id", "id"]),
    ];

    private static readonly Dictionary<string, BeadField> OfAnEdgeByKey =
        OfAnEdge.ToDictionary(field => field.Key, StringComparer.Ordinal);

    /// <summary>The names that a version of bd can give the meaning of an edge.</summary>
    public static IReadOnlyList<string> TypeOfAnEdge => OfAnEdgeByKey["type"].Candidates;

    /// <summary>The names that a version of bd can give the bead at the far end of an edge.</summary>
    public static IReadOnlyList<string> TargetOfAnEdge => OfAnEdgeByKey["target"].Candidates;

    private static readonly Dictionary<string, BeadField> OfACommentByKey =
        OfAComment.ToDictionary(field => field.Key, StringComparer.Ordinal);

    /// <summary>The names that a version of bd can give the text of a comment.</summary>
    public static IReadOnlyList<string> TextOfAComment => OfACommentByKey["text"].Candidates;

    /// <summary>The names that a version of bd can give the author of a comment.</summary>
    public static IReadOnlyList<string> AuthorOfAComment => OfACommentByKey["author"].Candidates;

    /// <summary>The names that a version of bd can give the moment that a comment was written.</summary>
    public static IReadOnlyList<string> CreatedOfAComment => OfACommentByKey["created"].Candidates;

    /// <summary>
    /// The names that a version of bd can give the list of beads which block a bead. Only the output
    /// of bd blocked carries it; a bead in a plain list does not.
    /// </summary>
    public static IReadOnlyList<string> BlockedByNames { get; } =
        ["blocked_by", "blockers", "blocked_by_ids"];

    /// <summary>
    /// The count of comments on a bead. This is not a field the UI shows; the probe reads it to find
    /// a bead that has comments to learn the names from.
    /// </summary>
    public static IReadOnlyList<string> CommentCountNames { get; } = ["comment_count", "comments_count"];

    /// <summary>Resolves each field to the name that these beads use, or to an empty string.</summary>
    public static IReadOnlyDictionary<string, string> ResolveFrom(IReadOnlyList<BeadRecord> sample) =>
        Resolve(All, sample);

    /// <summary>Resolves each comment field to the name that these comments use, or to an empty string.</summary>
    public static IReadOnlyDictionary<string, string> ResolveCommentsFrom(IReadOnlyList<BeadRecord> sample) =>
        Resolve(OfAComment, sample);

    private static IReadOnlyDictionary<string, string> Resolve(
        IReadOnlyList<BeadField> fields,
        IReadOnlyList<BeadRecord> sample)
    {
        var emitted = sample.SelectMany(record => record.FieldNames).ToHashSet(StringComparer.Ordinal);
        var resolved = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var field in fields)
        {
            resolved[field.Key] = field.Candidates.FirstOrDefault(emitted.Contains) ?? string.Empty;
        }

        return resolved;
    }
}
