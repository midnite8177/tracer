using AngleSharp.Dom;
using Bunit;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;
using DetailPage = JidokaUi.Web.Components.Pages.Detail;
using NeedsYouPage = JidokaUi.Web.Components.Pages.NeedsYou;

namespace JidokaUi.Tests.Boards;

/// <summary>
/// The answer panel as a browser draws it, on the detail page and in the needs-you view: the
/// options of a question with its recommendation, and the two writes that an answer makes. The
/// beads here carry no jidoka page, because the panel reads the metadata of the bead alone.
/// </summary>
public sealed class AnswerPanelMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";
    private const string TheComment = "comment b-7 Keep the dear plan";
    private const string TheLabelOff = "label remove b-7 human";

    private const string TheMetadata =
        """
        "metadata": {"lap.stage": "parked",
                     "question.options": "[{\"name\":\"Use the cheap plan\",\"confidence\":80},{\"name\":\"Keep the dear plan\",\"confidence\":20}]",
                     "question.recommended": "Use the cheap plan"}
        """;

    private static readonly string TheParkedBead =
        $$"""{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2, "status": "open", "labels": ["human"], {{TheMetadata}} }""";

    private const string TheAnsweredBead =
        """{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2, "status": "open", "labels": []}""";

    private const string TheAnswerAsACommentOnTheBead =
        """[{"text": "Keep the dear plan", "author": "jeff", "created_at": "2026-09-07T10:00:00Z"}]""";

    private readonly TwoProjects projects = new();

    [Fact]
    public void ShowsTheOptionsOfAParkedQuestionOnTheDetailPageWithTheirConfidence()
    {
        var page = TheDetailPageOfTheParkedBead();

        Assert.Equal(
            ["Use the cheap plan", "Keep the dear plan"],
            page.FindAll(".answer-panel .answer-press").Select(press => press.TextContent));
        Assert.Equal(
            ["80%", "20%"],
            page.FindAll(".answer-panel .answer-confidence").Select(sure => sure.TextContent));
    }

    [Fact]
    public void MarksTheRecommendedOptionOnTheDetailPageAndNoOtherOption()
    {
        var page = TheDetailPageOfTheParkedBead();

        var recommended = Assert.Single(page.FindAll(".answer-panel .answer-recommended"));
        Assert.Contains("Use the cheap plan", recommended.TextContent, StringComparison.Ordinal);
        Assert.Contains("Recommended", recommended.TextContent, StringComparison.Ordinal);
        Assert.Single(page.FindAll(".answer-panel .answer-recommended-mark"));
    }

    [Fact]
    public void CommentsTheOptionAndThenTakesTheHumanLabelOffWhenAPressPicksAnOption()
    {
        var page = TheDetailPageOfTheParkedBead();

        PressTheOption(page, "Keep the dear plan");

        page.WaitForAssertion(() => Assert.Equal([TheComment, TheLabelOff], TheWritesOfTheAnswer()));
    }

    [Fact]
    public void DrawsTheAnswerAsACommentAndNoPanelOnceThePageReadsTheAnsweredBeadAgain()
    {
        var page = TheDetailPageOfTheParkedBead();

        PressTheOption(page, "Keep the dear plan");

        page.WaitForAssertion(() => Assert.Empty(page.FindAll(".answer-panel")));
        Assert.Equal(
            ["Keep the dear plan"],
            page.FindAll(".bead-comment-text").Select(text => text.TextContent.Trim()));
    }

    [Fact]
    public void TakesNoLabelOffWhenTheCommentOfTheAnswerFails()
    {
        ABdThatTakesTheAnswer();
        projects.Bd.Fails(TheComment, "database is locked");
        var page = TheDetailPageOf(TheParkedBead);

        PressTheOption(page, "Keep the dear plan");

        page.WaitForAssertion(() =>
            Assert.Contains("database is locked", page.Find(".answer-panel .bead-write-message").TextContent, StringComparison.Ordinal));
        Assert.Equal([TheComment], TheWritesOfTheAnswer());
        Assert.Single(page.FindAll(".answer-panel"));
    }

    [Fact]
    public void SaysThatTheAnswerIsOnTheBeadWhenTheHumanLabelWillNotComeOff()
    {
        ABdThatTakesTheAnswer();
        projects.Bd.Fails(TheLabelOff, "label not found");
        var page = TheDetailPageOf(TheParkedBead);

        PressTheOption(page, "Keep the dear plan");

        page.WaitForAssertion(() =>
        {
            var said = page.Find(".answer-panel .bead-write-message").TextContent;
            Assert.Contains("Keep the dear plan", said, StringComparison.Ordinal);
            Assert.Contains("human label is still on", said, StringComparison.Ordinal);
        });
    }

    [Fact]
    public void PostsNoSecondCommentWhenALaterPressFollowsALabelThatWouldNotComeOff()
    {
        ABdThatTakesTheAnswer();
        projects.Bd.Fails(TheLabelOff, "label not found");
        var page = TheDetailPageOf(TheParkedBead);
        PressTheOption(page, "Keep the dear plan");
        page.WaitForAssertion(() => Assert.Contains("still on", page.Find(".answer-panel").TextContent, StringComparison.Ordinal));

        projects.Bd.Prints(TheLabelOff, string.Empty);
        PressTheOption(page, "Keep the dear plan");

        page.WaitForAssertion(() => Assert.Equal([TheComment, TheLabelOff, TheLabelOff], TheWritesOfTheAnswer()));
    }

    [Fact]
    public void DrawsNoPanelForABeadThatCarriesNoHumanLabel()
    {
        projects.Bd.DeclaresEveryWrite();
        var page = TheDetailPageOf(TheParkedBead.Replace("\"human\"", "\"docs\"", StringComparison.Ordinal));

        Assert.Empty(page.FindAll(".answer-panel"));
    }

    [Fact]
    public void DrawsNoPanelForABeadWhoseMetadataHoldsNoQuestion()
    {
        projects.Bd.DeclaresEveryWrite();
        var page = TheDetailPageOf(
            """{"id": "b-7", "title": "Pick a hosting plan", "status": "open", "labels": ["human"]}""");

        Assert.Empty(page.FindAll(".answer-panel"));
    }

    [Fact]
    public void RefusesInWordsAndTakesNoPressWhenBdHasNoCommentCommand()
    {
        projects.Bd.DeclaresEveryWrite().Prints("--help", """
            Working With Issues:
              label             Manage issue labels
              update            Update one or more issues
            """);
        var page = TheDetailPageOf(TheParkedBead);

        Assert.Contains("bd has no comment command", page.Find(".answer-panel .answer-refusal").TextContent, StringComparison.Ordinal);
        Assert.All(page.FindAll(".answer-press"), press => Assert.True(press.HasAttribute("disabled")));
    }

    [Fact]
    public void KeepsEveryOptionClosedAfterTheAnswerOutrunsTheWaitLimit()
    {
        ABdThatTakesTheAnswer();
        projects.Bd.Holds(TheComment);
        var page = TheDetailPageOf(TheParkedBead);

        PressTheOption(page, "Keep the dear plan");
        projects.Clock.Advance(JidokaUi.Core.Beads.BdAdapter.WaitLimit);

        page.WaitForAssertion(() =>
        {
            Assert.Contains("may still have landed", page.Find(".answer-panel .bead-write-message").TextContent, StringComparison.Ordinal);
            Assert.All(page.FindAll(".answer-press"), press => Assert.True(press.HasAttribute("disabled")));
        });
    }

    [Fact]
    public void DrawsThePanelUnderTheRowOfABeadThatCarriesAQuestionInTheNeedsYouView()
    {
        var view = TheNeedsYouViewOfTwoProjects();

        var panel = Assert.Single(view.FindAll("tr.needs-you-answer .answer-panel"));
        Assert.Equal(
            ["Use the cheap plan", "Keep the dear plan"],
            panel.QuerySelectorAll(".answer-press").Select(press => press.TextContent));
        Assert.Single(panel.QuerySelectorAll(".answer-recommended"));
        Assert.Equal(2, view.FindAll("tr.needs-you-row").Count);
    }

    [Fact]
    public void CommentsTheOptionAndTakesTheLabelOffFromTheNeedsYouViewAndTheBeadLeavesTheView()
    {
        var view = TheNeedsYouViewOfTwoProjects();

        PressTheOption(view, "Keep the dear plan");

        view.WaitForAssertion(() =>
        {
            Assert.Equal([TheComment, TheLabelOff], TheWritesOfTheAnswer());
            Assert.DoesNotContain("Pick a hosting plan", view.Markup, StringComparison.Ordinal);
        });
    }

    private static void PressTheOption(IRenderedComponent<DetailPage> page, string name) =>
        ThePressOf(page.FindAll(".answer-panel .answer-press"), name).Click();

    private static void PressTheOption(IRenderedComponent<NeedsYouPage> view, string name) =>
        ThePressOf(view.FindAll(".answer-panel .answer-press"), name).Click();

    private static IElement ThePressOf(IEnumerable<IElement> presses, string name) =>
        presses.Single(press => string.Equals(press.TextContent, name, StringComparison.Ordinal));

    private List<string> TheWritesOfTheAnswer() =>
        [.. projects.Bd.Invocations.Where(line =>
            (line.StartsWith("comment ", StringComparison.Ordinal) || line.StartsWith("label ", StringComparison.Ordinal))
            && !line.EndsWith("--help", StringComparison.Ordinal))];

    private IRenderedComponent<DetailPage> TheDetailPageOfTheParkedBead()
    {
        ABdThatTakesTheAnswer();
        return TheDetailPageOf(TheParkedBead);
    }

    // The scripts come first, so that a test replaces one of them with a failure afterwards.
    private void ABdThatTakesTheAnswer() =>
        projects.Bd
            .DeclaresEveryWrite()
            .Prints(TheComment, string.Empty)
            .Prints(TheLabelOff, string.Empty)
            .After(TheComment, bd => bd.PrintsIn(projects.Second.Value, "comments b-7 --json", TheAnswerAsACommentOnTheBead))
            .After(TheLabelOff, bd => bd
                .PrintsIn(projects.Second.Value, "show b-7 --json", $"[{TheAnsweredBead}]")
                .PrintsIn(projects.Second.Value, ListCommand, $"[{TheAnsweredBead}]"));

    private IRenderedComponent<DetailPage> TheDetailPageOf(string bead)
    {
        projects.Bd
            .PrintsIn(projects.Second.Value, "show b-7 --json", $"[{bead}]")
            .PrintsIn(projects.Second.Value, "comments b-7 --json", "[]")
            .PrintsIn(projects.Second.Value, ListCommand, $"[{bead}]")
            .PrintsIn(projects.First.Value, ListCommand, "[]");
        projects.RegisterOn(Services);
        Services.AddSingleton(new BeadDetailReader(projects.Adapter, new BacklogReader(projects.Adapter)));
        Services.GetRequiredService<Microsoft.AspNetCore.Components.NavigationManager>()
            .NavigateTo($"bead/b-7?project={Uri.EscapeDataString(projects.Second.Value)}");

        return Render<DetailPage>(parameters => parameters.Add(page => page.Id, "b-7"));
    }

    private IRenderedComponent<NeedsYouPage> TheNeedsYouViewOfTwoProjects()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints(TheComment, string.Empty)
            .Prints(TheLabelOff, string.Empty)
            .After(TheLabelOff, bd => bd.PrintsIn(projects.Second.Value, ListCommand, "[]"))
            .PrintsIn(
                projects.First.Value,
                ListCommand,
                """[{"id": "a-1", "title": "Decide the licence", "status": "open", "labels": ["human"]}]""")
            .PrintsIn(projects.Second.Value, ListCommand, $"[{TheParkedBead}]");
        projects.Selection.Select(projects.First);
        projects.RegisterOn(Services);
        Services.AddSingleton(new NeedsYouReader(projects.Catalog, projects.Backlogs));

        return Render<NeedsYouPage>();
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
