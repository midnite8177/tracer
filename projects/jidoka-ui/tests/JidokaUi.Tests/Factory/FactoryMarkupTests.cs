using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Factory;
using JidokaUi.Tests.Boards;
using DetailPage = JidokaUi.Web.Components.Pages.Detail;
using FactoryPage = JidokaUi.Web.Components.Pages.Factory;

namespace JidokaUi.Tests.Factory;

/// <summary>
/// The factory view and the task table of an epic's page as a browser draws them: which epics
/// stand, and the lap, the stage and the tries that each task shows.
/// </summary>
public sealed class FactoryMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string TheEpicAndItsTasks =
        """
        [
          {"id": "b", "title": "The site", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]},
          {"id": "b.1", "title": "Pick a hosting plan", "issue_type": "task", "status": "in_progress", "parent": "b",
           "metadata": {"lap.number": 2, "lap.stage": "build", "lap.tries": 1, "lap.trycap": 3, "lap.mergetries": 0, "lap.mergetrycap": 2}},
          {"id": "b.2", "title": "Launch the site", "issue_type": "task", "status": "open", "parent": "b"}
        ]
        """;

    private const string TheEpicOnItsOwn =
        """
        [{"id": "b", "title": "The site", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]}]
        """;

    private readonly TwoProjects projects = new();

    [Fact]
    public void ShowsTheLapTheStageAndTheTriesOfEachTaskOfAnEpicThatTheFactoryHolds()
    {
        var view = TheViewWhereTheSecondProjectHoldsAnEpic();

        Assert.Equal(
            [("Pick a hosting plan", "2", "build", "1/3"), ("Launch the site", "-", "no lap yet", "-")],
            view.FindAll("tr.factory-task").Select(RowOf));
    }

    [Fact]
    public void NamesTheEpicWithItsStateAndLeavesOutAProjectThatHoldsNone()
    {
        var view = TheViewWhereTheSecondProjectHoldsAnEpic();

        Assert.Equal("The site", view.Find("section.factory-epic h3 a").TextContent);
        Assert.Equal("running", view.Find(".factory-state").TextContent);
        Assert.Single(view.FindAll("h2"));
        Assert.Contains("second", view.Find("h2").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void LinksTheEpicAndEachTaskToItsBeadPageInTheProjectThatHoldsIt()
    {
        var view = TheViewWhereTheSecondProjectHoldsAnEpic();

        var project = Uri.EscapeDataString(projects.Second.Value);
        Assert.Equal($"bead/b?project={project}", view.Find("section.factory-epic h3 a").GetAttribute("href"));
        Assert.Equal(
            [$"bead/b.1?project={project}", $"bead/b.2?project={project}"],
            view.FindAll("tr.factory-task a").Select(link => link.GetAttribute("href")));
    }

    [Fact]
    public void SaysThatTheFactoryHoldsNoEpicWhenNoProjectHoldsOne()
    {
        projects.Bd
            .PrintsIn(projects.First.Value, ListCommand, "[]")
            .PrintsIn(projects.Second.Value, ListCommand, "[]");
        projects.RegisterOn(Services);
        Services.AddSingleton(new FactoryReader(projects.Catalog, projects.Backlogs));

        var view = Render<FactoryPage>();

        Assert.Contains("holds no epic", view.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void NamesTheProjectThatBdDidNotAnswerForAndStillShowsTheEpicsOfTheOthers()
    {
        projects.Bd.PrintsIn(projects.Second.Value, ListCommand, TheEpicOnItsOwn);
        projects.RegisterOn(Services);
        Services.AddSingleton(new FactoryReader(projects.Catalog, projects.Backlogs));

        var view = Render<FactoryPage>();

        Assert.Contains("first", view.Find("p.failure-message").TextContent, StringComparison.Ordinal);
        Assert.Equal("The site", view.Find("section.factory-epic h3 a").TextContent);
    }

    [Fact]
    public void ShowsTheTaskTableOnThePageOfAnEpicThatTheFactoryHolds()
    {
        var page = TheDetailPageOf(TheEpicOnItsOwn, TheEpicAndItsTasks);

        Assert.Equal(
            [("Pick a hosting plan", "2", "build", "1/3"), ("Launch the site", "-", "no lap yet", "-")],
            page.FindAll("section.bead-factory-tasks tr.factory-task").Select(RowOf));
    }

    [Fact]
    public void ShowsNoTaskTableOnThePageOfAnEpicThatTheFactoryDoesNotHold()
    {
        const string held = "\"labels\": [\"factory\"]";
        const string notHeld = "\"labels\": []";
        var page = TheDetailPageOf(TheEpicOnItsOwn.Replace(held, notHeld), TheEpicAndItsTasks.Replace(held, notHeld));

        Assert.Empty(page.FindAll("section.bead-factory-tasks"));
    }

    private static (string Task, string Lap, string Stage, string Tries) RowOf(AngleSharp.Dom.IElement row) =>
        (
            row.QuerySelector("a")?.TextContent ?? string.Empty,
            row.QuerySelector(".factory-lap")?.TextContent ?? string.Empty,
            row.QuerySelector(".factory-stage")?.TextContent ?? string.Empty,
            row.QuerySelector(".factory-tries")?.TextContent ?? string.Empty);

    private IRenderedComponent<FactoryPage> TheViewWhereTheSecondProjectHoldsAnEpic()
    {
        projects.Bd
            .PrintsIn(projects.First.Value, ListCommand, "[]")
            .PrintsIn(projects.Second.Value, ListCommand, TheEpicAndItsTasks);
        projects.RegisterOn(Services);
        Services.AddSingleton(new FactoryReader(projects.Catalog, projects.Backlogs));

        return Render<FactoryPage>();
    }

    private IRenderedComponent<DetailPage> TheDetailPageOf(string shown, string backlog)
    {
        const string id = "b";
        projects.Bd
            .PrintsIn(projects.Second.Value, $"show {id} --json", shown)
            .PrintsIn(projects.Second.Value, $"comments {id} --json", "[]")
            .PrintsIn(projects.Second.Value, ListCommand, backlog)
            .PrintsIn(projects.First.Value, ListCommand, "[]");
        projects.RegisterOn(Services);
        Services.AddSingleton(new BeadDetailReader(projects.Adapter, new BacklogReader(projects.Adapter)));
        Navigation.NavigateTo($"bead/{id}?project={Uri.EscapeDataString(projects.Second.Value)}");

        return Render<DetailPage>(parameters => parameters.Add(page => page.Id, id));
    }

    private NavigationManager Navigation => Services.GetRequiredService<NavigationManager>();

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
