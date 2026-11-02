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
    private const string StateCommand = "factory_state.py --json";

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
    public void NamesTheEpicWithNoStateChipInItsHeadingAndLeavesOutAProjectThatHoldsNone()
    {
        var view = TheViewWhereTheSecondProjectHoldsAnEpic();

        Assert.Equal("The site", view.Find("section.factory-epic h3 a").TextContent);
        Assert.Empty(view.FindAll("section.factory-epic h3 .pill-chip"));
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

    [Fact]
    public void ShowsTheFactoryStateAndTheNextStepOfEachEpicAtTheTopOfItsSection()
    {
        var view = TheViewWhereTheSecondProjectHoldsThreeEpics();

        Assert.Equal(
            new Dictionary<string, (string State, string Next)>
            {
                ["Running epic"] = ("running", "Nothing to do. The factory is running."),
                ["Asking epic"] = ("waiting on you", "Answer: Which plan? Answering wakes the factory by itself."),
                ["Stopped epic"] = ("stopped", "Run /jidoka:factory to start the manager again."),
            },
            view.FindAll("section.factory-epic").ToDictionary(
                section => section.QuerySelector("h3 a")?.TextContent ?? string.Empty,
                section => (
                    section.QuerySelector(".factory-drive-state")?.TextContent ?? string.Empty,
                    section.QuerySelector(".factory-drive-next")?.TextContent ?? string.Empty)));
        Assert.All(
            view.FindAll("section.factory-epic"),
            section => Assert.Contains("factory-drive", section.Children[1].ClassList));
    }

    [Fact]
    public void ShowsTheCommandToRunOnlyForTheEpicWhoseNextStepEndsWithIt()
    {
        var view = TheViewWhereTheSecondProjectHoldsThreeEpics();

        Assert.Equal(
            ["Stopped epic"],
            view.FindAll("section.factory-epic")
                .Where(section => section.QuerySelector(".factory-drive-command")?.TextContent == "/jidoka:factory")
                .Select(section => section.QuerySelector("h3 a")?.TextContent));
        Assert.Single(view.FindAll(".factory-drive-command"));
    }

    [Fact]
    public void ShowsTheTasksOfAnEpicBelowItsFactoryState()
    {
        var view = TheViewWhereTheSecondProjectHoldsThreeEpics();

        var running = view.FindAll("section.factory-epic")
            .Single(section => section.QuerySelector("h3 a")?.TextContent == "Running epic");
        Assert.Equal(["H3", "DIV", "TABLE"], running.Children.Select(child => child.TagName));
    }

    [Fact]
    public void SaysWhyTheStateScriptGaveNoStateWhileTheEpicsStillShow()
    {
        projects.Bd
            .PrintsIn(projects.First.Value, ListCommand, "[]")
            .PrintsIn(projects.Second.Value, ListCommand, TheEpicAndItsTasks);
        projects.Jidoka.Fails("factory_state.py --json", "factory_state: it could not read the beads");
        projects.RegisterOn(Services);
        Services.AddSingleton(new FactoryReader(projects.Catalog, projects.Backlogs));

        var view = Render<FactoryPage>();

        Assert.Contains(
            "it could not read the beads",
            view.Find("section.factory-epic .factory-drive-unread").TextContent,
            StringComparison.Ordinal);
        Assert.Empty(view.FindAll(".factory-drive-state"));
        Assert.Equal(2, view.FindAll("tr.factory-task").Count);
    }

    [Fact]
    public void ShowsTheNewStateOfAnEpicWhenItsProjectChanges()
    {
        var view = TheViewWhereTheSecondProjectHoldsThreeEpics();
        projects.Jidoka.Prints("factory_state.py --json", TheStates(TheStoppedEpicRuns));

        projects.Backlogs.Invalidate(projects.Second);

        view.WaitForAssertion(() => Assert.Empty(view.FindAll(".factory-drive-command")));
        Assert.Equal(
            ["running", "running", "waiting on you"],
            view.FindAll("section.factory-epic .factory-drive-state").Select(state => state.TextContent).Order());
    }

    [Fact]
    public void ShowsTheNewStateOfAnEpicWhenNoBeadChangedButTheRefreshIntervalPassed()
    {
        var view = TheViewWhereTheSecondProjectHoldsThreeEpics();
        Assert.Single(view.FindAll(".factory-drive-command"));
        projects.Jidoka.Prints("factory_state.py --json", TheStates(TheStoppedEpicRuns));

        projects.Clock.Advance(FactoryPage.StateRefresh);

        view.WaitForAssertion(() => Assert.Empty(view.FindAll(".factory-drive-command")));
        Assert.Equal(
            ["running", "running", "waiting on you"],
            view.FindAll("section.factory-epic .factory-drive-state").Select(state => state.TextContent).Order());
    }

    [Fact]
    public void RunsOneStateReadOfAProjectAtATimeAndFoldsTheChangesThatComeDuringItIntoOneReadAfter()
    {
        var view = TheViewWhereTheSecondProjectHoldsThreeEpics();
        projects.Jidoka.Holds(StateCommand);

        projects.Backlogs.Invalidate(projects.Second);
        projects.Backlogs.InvalidateFromWatch(projects.Second);
        projects.Backlogs.InvalidateFromWatch(projects.Second);
        projects.Clock.Advance(FactoryPage.StateRefresh);

        view.WaitForAssertion(() => Assert.Equal(2, StateReads()));
        Assert.Single(view.FindAll(".factory-drive-command"));
        projects.Jidoka.Prints(StateCommand, TheStates(TheStoppedEpicRuns));
        projects.Jidoka.Answers(StateCommand, TheStates(TheStoppedEpicIsStopped));

        view.WaitForAssertion(() => Assert.Empty(view.FindAll(".factory-drive-command")));
        Assert.Equal(3, StateReads());
        Assert.Equal(1, projects.Jidoka.MostRunsAtOnce);
    }

    [Fact]
    public void LinksEachBeadThatWaitsOnThePersonToItsPageInTheProjectThatHoldsIt()
    {
        var view = TheViewWhereTheSecondProjectHoldsThreeEpics();

        var asking = view.FindAll("section.factory-epic")
            .Single(section => section.QuerySelector("h3 a")?.TextContent == "Asking epic");
        Assert.Equal(
            [$"bead/w?project={Uri.EscapeDataString(projects.Second.Value)}"],
            asking.QuerySelectorAll("a.factory-drive-waiting").Select(link => link.GetAttribute("href")));
        Assert.Empty(view.FindAll("section.factory-epic")
            .Where(section => section != asking)
            .SelectMany(section => section.QuerySelectorAll("a.factory-drive-waiting")));
    }

    private const string ThreeEpics =
        """
        [
          {"id": "r", "title": "Running epic", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]},
          {"id": "r.1", "title": "A task", "issue_type": "task", "status": "open", "parent": "r"},
          {"id": "s", "title": "Stopped epic", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]},
          {"id": "w", "title": "Asking epic", "issue_type": "epic", "status": "in_progress", "labels": ["factory", "human"]}
        ]
        """;

    private const string TheStoppedEpicIsStopped =
        """
        {"epic": "s", "title": "Stopped epic", "state": "stopped", "heartbeat_age_seconds": null, "watcher": false,
         "waiting_on": [],
         "next_step": {"action": "restart", "text": "Run /jidoka:factory to start the manager again.",
                       "command": "/jidoka:factory", "run_after": null, "wakes_at": null, "wakes_on_answer": false}}
        """;

    private const string TheStoppedEpicRuns =
        """
        {"epic": "s", "title": "Stopped epic", "state": "running", "heartbeat_age_seconds": 1, "watcher": false,
         "waiting_on": [],
         "next_step": {"action": "none", "text": "Nothing to do. The factory is running.", "command": null,
                       "run_after": null, "wakes_at": null, "wakes_on_answer": false}}
        """;

    private static string TheStates(string stoppedEpic) =>
        $$$"""
        {"epics": [
          {"epic": "r", "title": "Running epic", "state": "running", "heartbeat_age_seconds": 5, "watcher": false,
           "waiting_on": [],
           "next_step": {"action": "none", "text": "Nothing to do. The factory is running.", "command": null,
                         "run_after": null, "wakes_at": null, "wakes_on_answer": false}},
          {{{stoppedEpic}}},
          {"epic": "w", "title": "Asking epic", "state": "waiting-on-you", "heartbeat_age_seconds": 9, "watcher": true,
           "waiting_on": [{"bead": "w", "kind": "question", "text": "Which plan?", "wakes": true}],
           "next_step": {"action": "answer", "text": "Answer: Which plan? Answering wakes the factory by itself.",
                         "command": null, "run_after": null, "wakes_at": null, "wakes_on_answer": true}}
        ]}
        """;

    private IRenderedComponent<FactoryPage> TheViewWhereTheSecondProjectHoldsThreeEpics()
    {
        projects.Bd
            .PrintsIn(projects.First.Value, ListCommand, "[]")
            .PrintsIn(projects.Second.Value, ListCommand, ThreeEpics);
        projects.Jidoka.Prints("factory_state.py --json", TheStates(TheStoppedEpicIsStopped));
        projects.RegisterOn(Services);
        Services.AddSingleton(new FactoryReader(projects.Catalog, projects.Backlogs));

        return Render<FactoryPage>();
    }

    private int StateReads() => projects.Jidoka.Invocations.Count(run => run == StateCommand);

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
