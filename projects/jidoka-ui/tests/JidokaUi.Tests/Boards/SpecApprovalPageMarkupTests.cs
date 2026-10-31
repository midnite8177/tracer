using AngleSharp.Dom;
using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Jidoka;
using ServedPage = JidokaUi.Web.Components.Pages.ServedPage;

namespace JidokaUi.Tests.Boards;

/// <summary>
/// The spec approval page as a browser draws it: the page that jidoka wrote beside an epic, each
/// proposed test case with its code beside its plain reading, and the answer panel in its slot. An
/// answer lands on the epic, and the panel grays once the epic has moved on.
/// </summary>
public sealed class SpecApprovalPageMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";
    private const string TheComment = "comment b-7 Approve";
    private const string TheLabelOff = "label remove b-7 human";

    private const string ThePage =
        """
        <!doctype html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <title>Spec approval: Approve the acceptance specs of Take card payments</title>
        <style>
        :root { --ink: #1c1f24; }
        .examples { display: grid; }
        </style>
        </head>
        <body>
        <header><p>Acceptance specs proposed for b-7</p><h1>Approve the acceptance specs of Take card payments</h1></header>
        <section class="cases">
        <h2>The test cases</h2>
        <article class="case">
        <h3>1. A shopper pays by card and the till prints a receipt</h3>
        <div class="examples">
        <div class="example"><h3>The spec</h3><pre><code>def test_a_shopper_pays_by_card(till):
            till.run("pay", "--card", "5.00")</code></pre></div>
        <div class="example"><h3>Plain reading</h3><p class="reading">Pay 5.00 by card and the till prints receipt 1.</p>
        <h3>If this feature were deleted</h3><p class="deletion">No. Without card payment there is no receipt, so the spec fails.</p></div>
        </div>
        </article>
        </section>
        <section class="interface"><h2>The interface table</h2>
        <table><thead><tr><th>Interface</th><th>Shape</th><th>Cases</th></tr></thead>
        <tbody><tr><td>Pay by card</td><td>`till pay --card &lt;amount&gt;`</td><td>1</td></tr></tbody></table>
        </section>
        <section class="answer-slot" data-jidoka-slot="answer-panel">
        <h2>Your answer</h2>
        <p>jidoka-ui draws the answer panel here. The bead holds the proposal in plain text.</p>
        </section>
        </body>
        </html>
        """;

    private const string TheMetadata =
        """
        "metadata": {"question.options": "[{\"name\":\"Approve\"},{\"name\":\"Ask back\"}]"}
        """;

    private static readonly string TheEpicWaitingForApproval =
        $$"""{"id": "b-7", "title": "Take card payments", "issue_type": "epic", "priority": 2, "status": "open", "labels": ["human"], {{TheMetadata}} }""";

    private static readonly string TheEpicTheHumanAnswered =
        $$"""{"id": "b-7", "title": "Take card payments", "issue_type": "epic", "priority": 2, "status": "open", "labels": [], {{TheMetadata}} }""";

    private const string TheAnswerAsACommentOnTheEpic =
        """[{"text": "Approve", "author": "jeff", "created_at": "2026-09-07T10:00:00Z"}]""";

    private readonly TwoProjects projects = new();

    [Fact]
    public void ShowsEachTestCaseWithItsCodeBesideItsPlainReadingAndItsDeletionAnswer()
    {
        var page = TheSpecApprovalPageOf(TheEpicWaitingForApproval);

        var onlyCase = page.Find(".jidoka-page .case");
        Assert.Contains("A shopper pays by card", onlyCase.QuerySelector("h3")?.TextContent, StringComparison.Ordinal);
        var sides = onlyCase.QuerySelectorAll(".examples > .example");
        Assert.Equal(2, sides.Length);
        Assert.Contains("till.run(\"pay\", \"--card\", \"5.00\")", sides[0].QuerySelector("pre code")?.TextContent, StringComparison.Ordinal);
        Assert.Equal("Pay 5.00 by card and the till prints receipt 1.", sides[1].QuerySelector(".reading")?.TextContent);
        Assert.Contains("the spec fails", sides[1].QuerySelector(".deletion")?.TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void ShowsApproveAndAskBackWithNoPercentBecauseNeitherCarriesAConfidence()
    {
        var page = TheSpecApprovalPageOf(TheEpicWaitingForApproval);

        Assert.Equal(
            ["Approve", "Ask back"],
            page.FindAll(".answer-panel .answer-press").Select(press => press.TextContent));
        Assert.Empty(page.FindAll(".answer-panel .answer-confidence"));
    }

    [Fact]
    public void WritesAnAnswerFromThePanelOntoTheEpicAndGraysTheControlsOnceTheEpicIsReadAgain()
    {
        projects.Bd
            .Prints(TheComment, string.Empty)
            .Prints(TheLabelOff, string.Empty)
            .After(TheComment, bd => bd.PrintsIn(projects.Second.Value, "comments b-7 --json", TheAnswerAsACommentOnTheEpic))
            .After(TheLabelOff, bd => bd
                .PrintsIn(projects.Second.Value, "show b-7 --json", $"[{TheEpicTheHumanAnswered}]")
                .PrintsIn(projects.Second.Value, ListCommand, $"[{TheEpicTheHumanAnswered}]"));
        var page = TheSpecApprovalPageOf(TheEpicWaitingForApproval);

        page.FindAll(".answer-panel .answer-press")
            .Single(press => string.Equals(press.TextContent, "Approve", StringComparison.Ordinal))
            .Click();

        page.WaitForAssertion(() => Assert.Single(page.FindAll(".answer-panel.answer-moved-on")));
        Assert.All(page.FindAll(".answer-press"), press => Assert.True(press.HasAttribute("disabled")));
        Assert.Contains("A shopper pays by card", page.Find(".jidoka-page .case").TextContent, StringComparison.Ordinal);
    }

    private IRenderedComponent<ServedPage> TheSpecApprovalPageOf(string epic)
    {
        projects.WritesAPage(JidokaPageKind.SpecApproval, "b-7", ThePage);
        projects.Bd
            .DeclaresEveryWrite()
            .PrintsIn(projects.Second.Value, "show b-7 --json", $"[{epic}]")
            .PrintsIn(projects.Second.Value, "comments b-7 --json", "[]")
            .PrintsIn(projects.Second.Value, ListCommand, $"[{epic}]")
            .PrintsIn(projects.First.Value, ListCommand, "[]");
        projects.RegisterOn(Services);
        Navigation.NavigateTo($"jidoka-page/spec-approval/b-7?project={Uri.EscapeDataString(projects.Second.Value)}");

        return Render<ServedPage>(parameters => parameters.Add(p => p.Kind, "spec-approval").Add(p => p.Id, "b-7"));
    }

    private NavigationManager Navigation => Services.GetRequiredService<NavigationManager>();

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
