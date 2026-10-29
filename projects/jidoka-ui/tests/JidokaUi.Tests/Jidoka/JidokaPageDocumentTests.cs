using JidokaUi.Core.Jidoka;

namespace JidokaUi.Tests.Jidoka;

public sealed class JidokaPageDocumentTests
{
    private const string AQuestionPage =
        """
        <!doctype html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <title>Question: Pick &amp; choose</title>
        <style>
        :root { --ink: #111; }
        @media (prefers-color-scheme: dark) { :root { --ink: #eee; } }
        body { margin: 0; }
        h1 { color: var(--ink); }
        </style>
        </head>
        <body>
        <header><h1>Pick a plan</h1></header>
        <section class="in-short"><p>Short.</p></section>
        <section class="answer-slot" data-jidoka-slot="answer-panel">
        <h2>Your answer</h2>
        <p>jidoka-ui draws the answer panel here.</p>
        </section>
        <footer>After the slot</footer>
        </body>
        </html>
        """;

    [Fact]
    public void ReadsTheTitleOfThePageAndDecodesItsEntities()
    {
        Assert.Equal("Question: Pick & choose", JidokaPageDocument.Parse(AQuestionPage).Title);
    }

    [Fact]
    public void SplitsTheBodyAtTheSlotThatThePageMarks()
    {
        var document = JidokaPageDocument.Parse(AQuestionPage);

        Assert.Collection(
            document.Parts,
            before =>
            {
                var markup = Assert.IsType<PageMarkup>(before);
                Assert.Contains("<h1>Pick a plan</h1>", markup.Html, StringComparison.Ordinal);
                Assert.DoesNotContain("data-jidoka-slot", markup.Html, StringComparison.Ordinal);
            },
            slot =>
            {
                var marked = Assert.IsType<PageSlot>(slot);
                Assert.Equal("answer-panel", marked.Name);
                Assert.Contains("jidoka-ui draws the answer panel here.", marked.Html, StringComparison.Ordinal);
            },
            after => Assert.Contains("After the slot", Assert.IsType<PageMarkup>(after).Html, StringComparison.Ordinal));
    }

    [Fact]
    public void KeepsNoHeadOrBodyTagInTheParts()
    {
        var document = JidokaPageDocument.Parse(AQuestionPage);

        var all = string.Concat(document.Parts.Select(part => part.Html));
        Assert.DoesNotContain("<body", all, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("<head>", all, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("<title", all, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("<style", all, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ClosesTheSlotAtItsOwnEndTagWhenSectionsNestInsideIt()
    {
        var document = JidokaPageDocument.Parse(
            """
            <body><section data-jidoka-slot="answer-panel"><section>inner</section>tail</section><p>after</p></body>
            """);

        var slot = Assert.IsType<PageSlot>(document.Parts[0]);
        Assert.Contains("tail", slot.Html, StringComparison.Ordinal);
        Assert.Equal("<p>after</p>", Assert.IsType<PageMarkup>(document.Parts[1]).Html);
    }

    [Fact]
    public void FindsEverySlotOfAPage()
    {
        var document = JidokaPageDocument.Parse(
            """
            <body><div data-jidoka-slot="one">1</div><p>mid</p><div data-jidoka-slot="two">2</div></body>
            """);

        Assert.Equal(["one", "two"], document.Parts.OfType<PageSlot>().Select(slot => slot.Name));
    }

    [Fact]
    public void ScopesTheStylesheetToTheElementThatHoldsThePage()
    {
        var document = JidokaPageDocument.Parse(AQuestionPage);

        Assert.StartsWith(".jidoka-page {", document.Style, StringComparison.Ordinal);
        Assert.DoesNotContain(":root", document.Style, StringComparison.Ordinal);
        Assert.DoesNotContain("body {", document.Style, StringComparison.Ordinal);
        Assert.Contains("& { --ink: #111; }", document.Style, StringComparison.Ordinal);
        Assert.Contains("h1 { color: var(--ink); }", document.Style, StringComparison.Ordinal);
    }

    [Fact]
    public void TakesAFragmentWithNoBodyTagAsTheWholeBody()
    {
        var document = JidokaPageDocument.Parse("<p>Only this</p>");

        Assert.Equal("<p>Only this</p>", Assert.IsType<PageMarkup>(Assert.Single(document.Parts)).Html);
        Assert.Equal(string.Empty, document.Title);
        Assert.Equal(string.Empty, document.Style);
    }
}
