using AngleSharp.Dom;
using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Projects;
using DetailPage = JidokaUi.Web.Components.Pages.Detail;
using ServedPage = JidokaUi.Web.Components.Pages.ServedPage;

namespace JidokaUi.Tests.Boards;

/// <summary>
/// A jidoka page as a browser draws it: the file that jidoka wrote beside its bead, with the
/// controls of the app in the slots that the file marks, and those controls gray once the bead
/// has moved on. The pages here are written to a temporary folder that stands for jidoka's home.
/// </summary>
public sealed class ServedPageMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";
    private const string TheComment = "comment b-7 Keep the dear plan";
    private const string TheLabelOff = "label remove b-7 human";

    private const string TheQuestionPage =
        """
        <!doctype html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <title>Question: Pick a hosting plan</title>
        <style>
        :root { --ink: #1c1f24; }
        body { margin: 0 auto; }
        h1 { color: var(--ink); }
        </style>
        </head>
        <body>
        <header><p>Question on b-7</p><h1>Pick a hosting plan</h1></header>
        <section class="in-short"><h2>In short</h2><p>The cheap plan caps traffic.</p></section>
        <section class="answer-slot" data-jidoka-slot="answer-panel">
        <h2>Your answer</h2>
        <p>jidoka-ui draws the answer panel here. The bead holds the question in plain text.</p>
        </section>
        </body>
        </html>
        """;

    private const string TheGatePage =
        """
        <html><head><title>Acceptance gate</title></head><body>
        <h1>Gate of e-1</h1>
        <section class="answer-slot" data-jidoka-slot="decide-panel">
        <p>jidoka-ui draws Merge and Drop here. Send back runs in /jidoka:accept.</p>
        </section>
        </body></html>
        """;

    private const string TheEpicAtTheGate =
        """
        {"id": "b-7", "title": "The site", "issue_type": "epic", "status": "in_progress",
         "labels": ["factory", "human"], "metadata": {"gate.state": "waiting"}}
        """;

    private const string TheEpicThatTheGateClosed =
        """
        {"id": "b-7", "title": "The site", "issue_type": "epic", "status": "closed", "close_reason": "Done",
         "labels": ["factory"], "metadata": {"gate.state": "merged"}}
        """;

    private const string TheEpicTheFactoryRuns =
        """{"id": "b-7", "title": "The site", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]}""";

    private const string TheMetadata =
        """
        "metadata": {"lap.stage": "parked",
                     "question.options": "[{\"name\":\"Use the cheap plan\",\"confidence\":80},{\"name\":\"Keep the dear plan\",\"confidence\":20}]",
                     "question.recommended": "Use the cheap plan"}
        """;

    private static readonly string TheParkedBead =
        $$"""{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2, "status": "open", "labels": ["human"], {{TheMetadata}} }""";

    private static readonly string TheAnsweredBead =
        $$"""{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2, "status": "open", "labels": [], {{TheMetadata}} }""";

    private static readonly string TheClosedBead =
        $$"""{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2, "status": "closed", "close_reason": "Done", "labels": ["human"], {{TheMetadata}} }""";

    private const string TheBeadWithNoQuestion =
        """{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2, "status": "open", "labels": []}""";

    private const string TheAnswerAsACommentOnTheBead =
        """[{"text": "Keep the dear plan", "author": "jeff", "created_at": "2026-09-07T10:00:00Z"}]""";

    private readonly TwoProjects projects = new();

    [Fact]
    public void ServesThePageThatJidokaWroteBesideTheBead()
    {
        var page = TheQuestionPageOf(TheParkedBead);

        Assert.Equal("Pick a hosting plan", page.Find(".jidoka-page h1").TextContent);
        Assert.Contains("The cheap plan caps traffic.", page.Find(".jidoka-page .in-short").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void ScopesTheStylesheetOfThePageToTheElementThatHoldsIt()
    {
        var page = TheQuestionPageOf(TheParkedBead);

        var style = page.Find("style.jidoka-page-style").TextContent;
        Assert.StartsWith(".jidoka-page {", style, StringComparison.Ordinal);
        Assert.DoesNotContain(":root", style, StringComparison.Ordinal);
        Assert.Empty(page.FindAll(".jidoka-page html, .jidoka-page body, .jidoka-page head"));
    }

    [Fact]
    public void LinksBackToTheBeadAndNamesItsPage()
    {
        var page = TheQuestionPageOf(TheParkedBead);

        var link = page.Find(".served-page-bar a");
        Assert.Equal(
            $"bead/b-7?project={Uri.EscapeDataString(projects.Second.Value)}",
            link.GetAttribute("href"));
        Assert.Contains("b-7", page.Find(".served-page-bar").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void DrawsTheAnswerPanelInTheSlotInPlaceOfItsPlaceholder()
    {
        var page = TheQuestionPageOf(TheParkedBead);

        var slot = page.Find(".jidoka-page [data-jidoka-slot='answer-panel']");
        Assert.Equal(
            ["Use the cheap plan", "Keep the dear plan"],
            slot.QuerySelectorAll(".answer-panel .answer-press").Select(press => press.TextContent));
        Assert.Single(slot.QuerySelectorAll(".answer-recommended"));
        Assert.DoesNotContain("jidoka-ui draws the answer panel here", page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void GraysTheControlsOnceTheAnswerLandedAndTheBeadIsReadAgain()
    {
        var page = TheQuestionPageOfABdThatTakesTheAnswer();

        PressTheOption(page, "Keep the dear plan");

        page.WaitForAssertion(() => Assert.Single(page.FindAll(".answer-panel.answer-moved-on")));
        Assert.All(page.FindAll(".answer-press"), press => Assert.True(press.HasAttribute("disabled")));
        Assert.Equal("Pick a hosting plan", page.Find(".jidoka-page h1").TextContent);
    }

    [Fact]
    public void GraysTheControlsOfAPageWhoseBeadMovedOnBeforeItLoaded()
    {
        var page = TheQuestionPageOf(TheAnsweredBead);

        var panel = page.Find(".answer-panel");
        Assert.Contains("answer-moved-on", panel.ClassList);
        Assert.Equal(
            ["Use the cheap plan", "Keep the dear plan"],
            panel.QuerySelectorAll(".answer-press").Select(press => press.TextContent));
        Assert.All(panel.QuerySelectorAll(".answer-press"), press => Assert.True(press.HasAttribute("disabled")));
        Assert.Contains("moved on", page.Find(".answer-moved-on-note").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void GraysTheControlsOfAPageWhoseBeadIsClosedEvenWithTheHumanLabelOn()
    {
        var page = TheQuestionPageOf(TheClosedBead);

        Assert.Single(page.FindAll(".answer-panel.answer-moved-on"));
        Assert.All(page.FindAll(".answer-press"), press => Assert.True(press.HasAttribute("disabled")));
    }

    [Fact]
    public void DrawsNoOptionsForABeadWhoseMetadataHoldsNoQuestionAndSaysThatItMovedOn()
    {
        var page = TheQuestionPageOf(TheBeadWithNoQuestion);

        Assert.Empty(page.FindAll(".answer-press"));
        Assert.Contains("moved on", page.Find("[data-jidoka-slot='answer-panel'] .answer-moved-on-note").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void GraysTheControlsWhenAnAgentTakesTheLabelOffWhileThePageIsOpen()
    {
        Directory.CreateDirectory(projects.Second.BeadsDirectory);
        var page = TheQuestionPageOf(TheParkedBead);
        Assert.Empty(page.FindAll(".answer-moved-on"));

        projects.Bd.PrintsIn(projects.Second.Value, "show b-7 --json", $"[{TheAnsweredBead}]");
        projects.WriteReports.ReportWrite(projects.Second.BeadsDirectory);

        page.WaitForAssertion(
            () => Assert.Single(page.FindAll(".answer-panel.answer-moved-on")),
            ABacklogCache.LongEnoughForAStrayInvalidationToLand(ProjectWatchers.QuietPeriod));
    }

    [Fact]
    public void DrawsMergeAndDropInTheDecideSlotInPlaceOfItsPlaceholder()
    {
        var page = TheGatePageOf(TheEpicAtTheGate);

        var slot = page.Find(".jidoka-page [data-jidoka-slot='decide-panel']");
        Assert.Equal(["Merge", "Drop"], slot.QuerySelectorAll(".gate-box button").Select(press => press.TextContent));
        Assert.DoesNotContain("jidoka-ui draws Merge and Send back here", page.Markup, StringComparison.Ordinal);
        Assert.Empty(page.FindAll(".answer-panel"));
    }

    [Fact]
    public void DrawsNoSendBackButtonAnywhereOnTheGatePage()
    {
        var page = TheGatePageOf(TheEpicAtTheGate);

        Assert.DoesNotContain(
            page.FindAll("button"),
            press => press.TextContent.Contains("Send back", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void GraysTheGateControlsOnceTheDecisionLandedAndTheEpicIsReadAgain()
    {
        projects.Jidoka
            .Prints("gate.py merge b-7 --message=Add the site", "4f2a9c1")
            .After("gate.py merge b-7 --message=Add the site", () => projects.Bd
                .PrintsIn(projects.Second.Value, "show b-7 --json", $"[{TheEpicThatTheGateClosed}]")
                .PrintsIn(projects.Second.Value, ListCommand, $"[{TheEpicThatTheGateClosed}]"));
        var page = TheGatePageOf(TheEpicAtTheGate);

        page.Find("#gate-message").Input("Add the site");
        page.Find(".gate-merge").Click();

        page.WaitForAssertion(() => Assert.Single(page.FindAll(".gate-box.gate-moved-on")));
        Assert.All(page.FindAll(".gate-box button"), press => Assert.True(press.HasAttribute("disabled")));
        Assert.Contains("4f2a9c1", page.Find(".gate-box .bead-write-message").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void GraysTheGateControlsOfAPageWhoseEpicDoesNotWaitAtTheGate()
    {
        var page = TheGatePageOf(TheEpicTheFactoryRuns);

        var box = page.Find(".gate-box");
        Assert.Contains("gate-moved-on", box.ClassList);
        Assert.Equal(["Merge", "Drop"], box.QuerySelectorAll("button").Select(press => press.TextContent));
        Assert.All(box.QuerySelectorAll("button"), press => Assert.True(press.HasAttribute("disabled")));
        Assert.Contains("no longer waits", box.TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void GraysTheGateControlsOfAClosedEpicThatStillCarriesTheWaitingState()
    {
        var page = TheGatePageOf(TheEpicAtTheGate.Replace("in_progress", "closed", StringComparison.Ordinal));

        Assert.Single(page.FindAll(".gate-box.gate-moved-on"));
        Assert.All(page.FindAll(".gate-box button"), press => Assert.True(press.HasAttribute("disabled")));
    }

    [Fact]
    public void KeepsThePlaceholderOfASlotThatTheAppHasNoControlFor()
    {
        projects.WritesAPage(
            JidokaPageKind.Gate,
            "b-7",
            TheGatePage.Replace("decide-panel", "send-back-panel", StringComparison.Ordinal));
        var page = TheServedPageOf("gate", TheEpicAtTheGate);

        var slot = page.Find(".jidoka-page [data-jidoka-slot='send-back-panel']");
        Assert.Contains("jidoka-ui draws Merge and Drop here. Send back runs in /jidoka:accept.", slot.TextContent, StringComparison.Ordinal);
        Assert.Empty(page.FindAll(".gate-box"));
    }

    [Fact]
    public void SaysThatJidokaWroteNoPageWhenNoneSitsBesideTheBead()
    {
        var page = TheServedPageOf("question", TheParkedBead);

        Assert.Contains("no question page", page.Find(".served-page-missing").TextContent, StringComparison.Ordinal);
        Assert.Empty(page.FindAll(".jidoka-page"));
    }

    [Fact]
    public void SaysThatNoSuchKindOfPageExistsForAWordThatNamesNoKind()
    {
        var page = TheServedPageOf("report", TheParkedBead);

        Assert.Contains("report", page.Find(".served-page-missing").TextContent, StringComparison.Ordinal);
        Assert.Empty(page.FindAll(".jidoka-page"));
    }

    [Fact]
    public void ShowsThePageAndNoControlsWhenBdWillNotGiveTheBead()
    {
        projects.WritesAPage(JidokaPageKind.Question, "b-7", TheQuestionPage);
        projects.Bd.Fails("show b-7 --json", "database is locked");
        projects.RegisterOn(Services);
        Navigation.NavigateTo(TheAddressOf("question"));

        var page = Render<ServedPage>(parameters => parameters.Add(p => p.Kind, "question").Add(p => p.Id, "b-7"));

        Assert.Contains("database is locked", page.Find(".bead-message").TextContent, StringComparison.Ordinal);
        Assert.Equal("Pick a hosting plan", page.Find(".jidoka-page h1").TextContent);
        Assert.Empty(page.FindAll(".answer-panel"));
    }

    [Fact]
    public void LinksTheDetailPageOfTheBeadToEachPageThatSitsBesideIt()
    {
        projects.WritesAPage(JidokaPageKind.Question, "b-7", TheQuestionPage);
        projects.WritesAPage(JidokaPageKind.Gate, "b-7", TheGatePage);
        projects.Bd
            .DeclaresEveryWrite()
            .PrintsIn(projects.Second.Value, "show b-7 --json", $"[{TheParkedBead}]")
            .PrintsIn(projects.Second.Value, "comments b-7 --json", "[]")
            .PrintsIn(projects.Second.Value, ListCommand, $"[{TheParkedBead}]")
            .PrintsIn(projects.First.Value, ListCommand, "[]");
        projects.RegisterOn(Services);
        Services.AddSingleton(new BeadDetailReader(projects.Adapter, new BacklogReader(projects.Adapter)));
        Navigation.NavigateTo($"bead/b-7?project={Uri.EscapeDataString(projects.Second.Value)}");

        var detail = Render<DetailPage>(parameters => parameters.Add(p => p.Id, "b-7"));

        var links = detail.FindAll("a.jidoka-page-link");
        Assert.Equal(
            [
                $"jidoka-page/question/b-7?project={Uri.EscapeDataString(projects.Second.Value)}",
                $"jidoka-page/gate/b-7?project={Uri.EscapeDataString(projects.Second.Value)}",
            ],
            links.Select(link => link.GetAttribute("href")));
    }

    private static void PressTheOption(IRenderedComponent<ServedPage> page, string name) =>
        page.FindAll(".answer-panel .answer-press")
            .Single(press => string.Equals(press.TextContent, name, StringComparison.Ordinal))
            .Click();

    private IRenderedComponent<ServedPage> TheQuestionPageOfABdThatTakesTheAnswer()
    {
        projects.Bd
            .Prints(TheComment, string.Empty)
            .Prints(TheLabelOff, string.Empty)
            .After(TheComment, bd => bd.PrintsIn(projects.Second.Value, "comments b-7 --json", TheAnswerAsACommentOnTheBead))
            .After(TheLabelOff, bd => bd
                .PrintsIn(projects.Second.Value, "show b-7 --json", $"[{TheAnsweredBead}]")
                .PrintsIn(projects.Second.Value, ListCommand, $"[{TheAnsweredBead}]"));
        return TheQuestionPageOf(TheParkedBead);
    }

    private IRenderedComponent<ServedPage> TheQuestionPageOf(string bead)
    {
        projects.WritesAPage(JidokaPageKind.Question, "b-7", TheQuestionPage);
        return TheServedPageOf("question", bead);
    }

    private IRenderedComponent<ServedPage> TheGatePageOf(string epic)
    {
        projects.WritesAPage(JidokaPageKind.Gate, "b-7", TheGatePage);
        return TheServedPageOf("gate", epic);
    }

    private IRenderedComponent<ServedPage> TheServedPageOf(string kind, string bead)
    {
        projects.Bd
            .DeclaresEveryWrite()
            .PrintsIn(projects.Second.Value, "show b-7 --json", $"[{bead}]")
            .PrintsIn(projects.Second.Value, "comments b-7 --json", "[]")
            .PrintsIn(projects.Second.Value, ListCommand, $"[{bead}]")
            .PrintsIn(projects.First.Value, ListCommand, "[]");
        projects.RegisterOn(Services);
        Navigation.NavigateTo(TheAddressOf(kind));

        return Render<ServedPage>(parameters => parameters.Add(p => p.Kind, kind).Add(p => p.Id, "b-7"));
    }

    private string TheAddressOf(string kind) =>
        $"jidoka-page/{kind}/b-7?project={Uri.EscapeDataString(projects.Second.Value)}";

    private NavigationManager Navigation => Services.GetRequiredService<NavigationManager>();

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
