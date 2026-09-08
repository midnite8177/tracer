using Markdig;

namespace TracerUi.Core.Boards;

/// <summary>
/// Renders the prose of a bead as HTML. The description, the acceptance criteria and the notes are
/// markdown, so the Demo and the Seams sections read as sections and not as one run of text.
/// </summary>
public static class BeadMarkdown
{
    // Raw HTML never reaches the page. An agent and a person both write these fields, and the page
    // puts the answer into the document without a further escape.
    private static readonly MarkdownPipeline Pipeline =
        new MarkdownPipelineBuilder().DisableHtml().UseAutoLinks().Build();

    /// <summary>The HTML of this markdown, or an empty string when the text is empty.</summary>
    public static string ToHtml(string markdown) =>
        markdown.Length == 0 ? string.Empty : Markdown.ToHtml(markdown, Pipeline);
}
