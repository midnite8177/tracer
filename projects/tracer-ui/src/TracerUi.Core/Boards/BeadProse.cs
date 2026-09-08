namespace TracerUi.Core.Boards;

/// <summary>
/// The prose of one bead. Each field is markdown, so the detail page renders it rather than showing
/// it as one run of text. These three travel together everywhere a bead is read or shown.
/// </summary>
/// <param name="Acceptance">The acceptance criteria, or an empty string when the bead states none.</param>
/// <param name="Notes">The notes, or an empty string when the bead carries none.</param>
public sealed record BeadProse(string Description, string Acceptance, string Notes)
{
    public static BeadProse None { get; } = new(string.Empty, string.Empty, string.Empty);

    /// <summary>The Demo line of the description, or an empty string when it has none.</summary>
    public string DemoLine => Boards.DemoLine.In(Description);

    /// <summary>
    /// True when the description carries a Demo line. An epic states none of its own, so this is
    /// false for every epic.
    /// </summary>
    public bool HasDemoLine => DemoLine.Length > 0;

    public bool HasDescription => Description.Length > 0;

    public bool HasAcceptance => Acceptance.Length > 0;

    public bool HasNotes => Notes.Length > 0;

    /// <summary>
    /// True when the bead states neither acceptance criteria nor notes. A description that is absent
    /// is not part of it: a bead that needs one must say so, and no line hides that.
    /// </summary>
    public bool StatesNoAcceptanceAndNoNotes => !HasAcceptance && !HasNotes;

    public string DescriptionHtml => BeadMarkdown.ToHtml(Description);

    public string AcceptanceHtml => BeadMarkdown.ToHtml(Acceptance);

    public string NotesHtml => BeadMarkdown.ToHtml(Notes);
}
