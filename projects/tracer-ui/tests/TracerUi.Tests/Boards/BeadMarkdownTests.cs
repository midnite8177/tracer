using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BeadMarkdownTests
{
    [Fact]
    public void RendersTheHeadingsAndTheParagraphsOfADescription()
    {
        var html = BeadMarkdown.ToHtml("## Demo\n\nBrowse the board.\n");

        Assert.Contains("<h2", html);
        Assert.Contains("Demo", html);
        Assert.Contains("<p>Browse the board.</p>", html);
    }

    [Fact]
    public void RendersABulletListAndInlineCode()
    {
        var html = BeadMarkdown.ToHtml("- one\n- `bd ready`\n");

        Assert.Contains("<li>one</li>", html);
        Assert.Contains("<code>bd ready</code>", html);
    }

    [Fact]
    public void RefusesToPassRawHtmlThroughIntoThePage()
    {
        var html = BeadMarkdown.ToHtml("<script>alert(1)</script>\n");

        Assert.DoesNotContain("<script>", html);
        Assert.Contains("&lt;script&gt;", html);
    }

    [Fact]
    public void RendersNothingForATextThatIsEmpty()
    {
        Assert.Equal(string.Empty, BeadMarkdown.ToHtml(string.Empty));
    }
}
