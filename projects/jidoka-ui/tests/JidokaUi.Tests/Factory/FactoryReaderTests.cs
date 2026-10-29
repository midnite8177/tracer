using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Factory;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;
using JidokaUi.Tests.Projects;

namespace JidokaUi.Tests.Factory;

public sealed class FactoryReaderTests
{
    private const string ListCommand = "list --all --limit 0 --json";

    private static readonly ProjectPath First = ProjectPath.From(Path.Combine(Path.GetTempPath(), "first"));
    private static readonly ProjectPath Second = ProjectPath.From(Path.Combine(Path.GetTempPath(), "second"));

    [Fact]
    public async Task ListsEveryEpicThatTheFactoryHoldsInEveryProjectWithTheProjectOfEach()
    {
        var bd = ABdThatAnswersBoth(
            """[{"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": ["factory"]}]""",
            """[{"id": "b", "title": "The site", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]}]""");

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        Assert.Equal(
            [(First, "The parser"), (Second, "The site")],
            view.Projects.SelectMany(project => project.Epics.Select(epic => (project.Project, epic.Epic.Title))));
    }

    [Fact]
    public async Task LeavesOutAnEpicWithoutTheFactoryLabelAndAClosedOne()
    {
        var bd = ABdThatAnswersBoth(
            """
            [
              {"id": "a", "title": "Held", "issue_type": "epic", "status": "open", "labels": ["factory"]},
              {"id": "b", "title": "Never handed off", "issue_type": "epic", "status": "open"},
              {"id": "c", "title": "Accepted", "issue_type": "epic", "status": "closed", "labels": ["factory"]},
              {"id": "d", "title": "A task with the label", "issue_type": "task", "status": "open", "labels": ["factory"]}
            ]
            """,
            "[]");

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        Assert.Equal(["Held"], view.Projects.SelectMany(project => project.Epics).Select(epic => epic.Epic.Title));
    }

    [Fact]
    public async Task GivesEachTaskOfAnEpicItsLapItsStageAndItsTriesAgainstTheCapOfThatStage()
    {
        var bd = ABdThatAnswersBoth(
            """
            [
              {"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": ["factory"]},
              {"id": "a.1", "title": "Read the header", "issue_type": "task", "status": "in_progress", "parent": "a",
               "metadata": {"lap.number": 2, "lap.stage": "build", "lap.tries": 1, "lap.mergetries": 0}},
              {"id": "a.2", "title": "Join the rows", "issue_type": "task", "status": "in_progress", "parent": "a",
               "metadata": {"lap.number": 1, "lap.stage": "merge", "lap.tries": 2, "lap.mergetries": 1}}
            ]
            """,
            "[]");

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        var tasks = Assert.Single(view.Projects[0].Epics).Tasks;
        Assert.Equal(
            [("a.1", "2", "build", "1/3"), ("a.2", "1", "merge", "1/2")],
            tasks.Select(task => (task.Id, task.Lap, task.Stage, task.Tries)));
    }

    [Fact]
    public async Task SaysMergedForAClosedTaskThatHeldALapAndNoLapYetForAnOpenTaskThatHeldNone()
    {
        var bd = ABdThatAnswersBoth(
            """
            [
              {"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": ["factory"]},
              {"id": "a.1", "title": "Read the header", "issue_type": "task", "status": "closed", "parent": "a",
               "metadata": {"lap.number": 3, "lap.stage": "build", "lap.tries": 1}},
              {"id": "a.2", "title": "Join the rows", "issue_type": "task", "status": "open", "parent": "a"}
            ]
            """,
            "[]");

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        var tasks = Assert.Single(view.Projects[0].Epics).Tasks;
        Assert.Equal(
            [("a.1", "3", "merged", "-"), ("a.2", "-", "no lap yet", "-")],
            tasks.Select(task => (task.Id, task.Lap, task.Stage, task.Tries)));
    }

    [Fact]
    public async Task ReadsTheStateOfAnEpicFromTheHumanLabelAndTheGate()
    {
        var bd = ABdThatAnswersBoth(
            """
            [
              {"id": "a", "title": "Running", "issue_type": "epic", "status": "open", "labels": ["factory"]},
              {"id": "b", "title": "Parked", "issue_type": "epic", "status": "open", "labels": ["factory", "human"]},
              {"id": "c", "title": "Gated", "issue_type": "epic", "status": "open", "labels": ["factory"],
               "metadata": {"gate.state": "waiting"}}
            ]
            """,
            "[]");

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        Assert.Equal(
            [("Running", EpicState.Running), ("Parked", EpicState.Parked), ("Gated", EpicState.AtTheGate)],
            view.Projects[0].Epics.Select(epic => (epic.Epic.Title, epic.State)));
        Assert.Equal("at the acceptance gate", EpicState.AtTheGate.Words());
    }

    [Fact]
    public async Task ReadsOneProjectAgainAndLeavesTheEpicsOfTheOthersAsTheyWere()
    {
        var bd = ABdThatAnswersBoth(
            """[{"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": ["factory"]}]""",
            """[{"id": "b", "title": "The site", "issue_type": "epic", "status": "open", "labels": ["factory"]}]""");
        var reader = ReaderOver(bd, First, Second);
        var view = await reader.ReadAsync();

        var again = view.With(await reader.ReadAsync(Second));

        Assert.Equal(
            ["The parser", "The site"],
            again.Projects.SelectMany(project => project.Epics).Select(epic => epic.Epic.Title));
        Assert.Equal(1, bd.Runs(First.Value, ListCommand));
    }

    private static FakeBd ABdThatAnswersBoth(string firstList, string secondList) =>
        new FakeBd()
            .PrintsIn(First.Value, ListCommand, firstList)
            .PrintsIn(Second.Value, ListCommand, secondList)
            .Prints("ready --json", "[]")
            .Prints("blocked --json", "[]");

    private static FactoryReader ReaderOver(FakeBd bd, params ProjectPath[] projects)
    {
        var store = new InMemoryProjectRegistryStore();
        store.Hold(ProjectRegistry.Empty with { Projects = [.. projects] });
        var adapter = new BdAdapter(bd, TimeProvider.System);
        return new FactoryReader(
            new ProjectCatalog(store, adapter, new NoOnboardedProjects()),
            new BacklogCache(new BacklogReader(adapter), adapter));
    }
}
