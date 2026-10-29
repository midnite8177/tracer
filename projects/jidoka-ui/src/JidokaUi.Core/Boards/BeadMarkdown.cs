using Markdig;

namespace JidokaUi.Core.Boards;

/// <summary>
/// Renders the prose of a bead as HTML. The description, the acceptance criteria and the notes are
/// markdown, so the Demo and the Seams sections read as sections and not as one run of text. A
/// comment is markdown too, and it keeps the line breaks of its author, because the author lays
/// out a comment line by line, text diagrams included.
/// </summary>
public static class BeadMarkdown
{
    private static readonly MarkdownPipeline Pipeline =
        new MarkdownPipelineBuilder().DisableHtml().UseAutoLinks().Build();

    private static readonly MarkdownPipeline CommentPipeline =
        new MarkdownPipelineBuilder().DisableHtml().UseAutoLinks().UseSoftlineBreakAsHardlineBreak().Build();

    /// <summary>The HTML of this markdown, or an empty string when the text is empty.</summary>
    public static string ToHtml(string markdown) =>
        markdown.Length == 0 ? string.Empty : Markdown.ToHtml(markdown, Pipeline);

    /// <summary>
    /// The HTML of a comment, or an empty string when the text is empty. A line break inside a
    /// paragraph stays a line break, and a fenced or indented block keeps every space.
    /// </summary>
    public static string ToCommentHtml(string markdown) =>
        markdown.Length == 0 ? string.Empty : Markdown.ToHtml(markdown, CommentPipeline);
}
