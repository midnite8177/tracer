using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;
using TracerUi.Tests.Projects;

namespace TracerUi.Tests.Boards;

public sealed class NeedsYouReaderTests
{
    private const string ListCommand = "list --all --limit 0 --json";

    private static readonly ProjectPath First = ProjectPath.From(Path.Combine(Path.GetTempPath(), "first"));
    private static readonly ProjectPath Second = ProjectPath.From(Path.Combine(Path.GetTempPath(), "second"));

    [Fact]
    public async Task GathersTheBeadsThatNeedYouFromEveryProjectAndNamesTheProjectOfEachOne()
    {
        var bd = ABdThatAnswersBoth(
            """
            [
              {"id": "a-1", "title": "Decide the licence", "status": "open", "labels": ["human"]},
              {"id": "a-2", "title": "Write the parser", "status": "open", "labels": []}
            ]
            """,
            """
            [
              {"id": "b-7", "title": "Pick a hosting plan", "status": "open", "labels": ["human"]}
            ]
            """);

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        Assert.Equal(
            [(First, "Decide the licence"), (Second, "Pick a hosting plan")],
            TitlesWithTheirProjects(view));
    }

    [Fact]
    public async Task NamesTheProjectThatBdDidNotAnswerForAndStillGivesTheBeadsOfTheOthers()
    {
        var bd = new FakeBd()
            .PrintsIn(
                First.Value,
                ListCommand,
                """[{"id": "a-1", "title": "Decide the licence", "status": "open", "labels": ["human"]}]""")
            .Prints("ready --json", "[]")
            .Prints("blocked --json", "[]");

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        Assert.Equal([(First, "Decide the licence")], TitlesWithTheirProjects(view));
        var unread = Assert.Single(view.Projects, project => project.IsUnread);
        Assert.Equal(Second, unread.Project);
        Assert.Contains("unknown command", unread.Reason);
    }

    [Fact]
    public async Task DropsAClosedBeadThatStillCarriesTheHumanLabel()
    {
        var bd = ABdThatAnswersBoth(
            """
            [
              {"id": "a-1", "title": "Decide the licence", "status": "closed", "labels": ["human"]},
              {"id": "a-2", "title": "Pick a name", "status": "open", "labels": ["human"]}
            ]
            """,
            "[]");

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        Assert.Equal([(First, "Pick a name")], TitlesWithTheirProjects(view));
    }

    [Fact]
    public async Task KeepsAnEpicThatWaitsOnAPerson()
    {
        var bd = ABdThatAnswersBoth(
            """
            [
              {"id": "a", "title": "The migration", "issue_type": "epic", "status": "in_progress", "labels": ["human"]}
            ]
            """,
            "[]");

        var view = await ReaderOver(bd, First, Second).ReadAsync();

        Assert.Equal([(First, "The migration")], TitlesWithTheirProjects(view));
    }

    [Fact]
    public async Task ReadsOneProjectAgainAndLeavesTheBeadsOfTheOthersAsTheyWere()
    {
        var bd = ABdThatAnswersBoth(
            """[{"id": "a-1", "title": "Decide the licence", "status": "open", "labels": ["human"]}]""",
            """[{"id": "b-7", "title": "Pick a hosting plan", "status": "open", "labels": ["human"]}]""");
        var reader = ReaderOver(bd, First, Second);
        var view = await reader.ReadAsync();

        var again = view.With(await reader.ReadAsync(Second));

        Assert.Equal(
            [(First, "Decide the licence"), (Second, "Pick a hosting plan")],
            TitlesWithTheirProjects(again));
        Assert.Equal(1, bd.Runs(First.Value, ListCommand));
    }

    // Every bead that the view shows, with the project that holds it, in the order it shows them.
    private static IEnumerable<(ProjectPath Project, string Title)> TitlesWithTheirProjects(NeedsYouView view) =>
        view.Projects.SelectMany(project => project.Beads.Select(bead => (project.Project, bead.Title)));

    private static FakeBd ABdThatAnswersBoth(string firstList, string secondList) =>
        new FakeBd()
            .PrintsIn(First.Value, ListCommand, firstList)
            .PrintsIn(Second.Value, ListCommand, secondList)
            .Prints("ready --json", "[]")
            .Prints("blocked --json", "[]");

    private static NeedsYouReader ReaderOver(FakeBd bd, params ProjectPath[] projects)
    {
        var store = new InMemoryProjectRegistryStore();
        store.Save(ProjectRegistry.Empty with { Projects = [.. projects] });
        var adapter = new BdAdapter(bd);
        return new NeedsYouReader(
            new ProjectCatalog(store, adapter),
            new BacklogCache(new BacklogReader(adapter), adapter));
    }
}
