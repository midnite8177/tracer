using Bunit;
using Bunit.TestDoubles;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using BoardPage = TracerUi.Web.Components.Pages.Board;

namespace TracerUi.Tests.Boards;

/// <summary>The board as a browser draws it, and the project that its own address names.</summary>
public sealed class BoardAddressMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string TheReadOfTheBeads = "ready --json";

    // Both projects hold beads with the same ids and other titles, so a selection or a collapsed
    // row that one project left behind would show on the board of the other.
    private const string TheBeadsOfTheFirstProject =
        """
        [{"id": "s", "title": "The first epic", "issue_type": "epic", "priority": 2, "status": "open"},
         {"id": "s-1", "title": "Held in the first", "issue_type": "task", "priority": 2, "status": "open",
          "parent": "s"},
         {"id": "s-2", "title": "Loose in the first", "issue_type": "task", "priority": 2, "status": "open"}]
        """;

    private const string TheBeadsOfTheFirstProjectAfterAChange =
        """
        [{"id": "s", "title": "The first epic", "issue_type": "epic", "priority": 2, "status": "open"},
         {"id": "s-1", "title": "Held in the first", "issue_type": "task", "priority": 2, "status": "open",
          "parent": "s"},
         {"id": "s-2", "title": "Loose in the first", "issue_type": "task", "priority": 2, "status": "open"},
         {"id": "s-3", "title": "New in the first", "issue_type": "task", "priority": 2, "status": "open"}]
        """;

    private const string TheBeadsOfTheSecondProject =
        """
        [{"id": "s", "title": "The second epic", "issue_type": "epic", "priority": 2, "status": "open"},
         {"id": "s-1", "title": "Held bug in the second", "issue_type": "bug", "priority": 2, "status": "open",
          "parent": "s"},
         {"id": "s-2", "title": "Loose in the second", "issue_type": "task", "priority": 2, "status": "open"}]
        """;

    private const string TheBoardWords = "so this address names no project whose board it can show.";

    private readonly TwoProjects projects = new();

    [Fact]
    public void ShowsTheBeadsOfTheProjectThatItsAddressNamesWithTheFilterOfTheAddress()
    {
        var board = TheBoardAt(
            BoardFilterAddress.Of(projects.Second, BoardFilter.Everything with { Type = "bug" }),
            theActiveProject: projects.First);

        Assert.Equal(["The second epic", "Held bug in the second"], TheTitles(board));
    }

    [Fact]
    public void MakesTheProjectThatItsAddressNamesTheActiveOne()
    {
        TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: projects.First);

        Assert.Equal(projects.Second, projects.Selection.Current);
    }

    [Fact]
    public void ReplacesAnAddressThatNamesNoProjectWithOneThatNamesTheProjectOfTheTabAndKeepsItsFilter()
    {
        var board = TheBoardAt("board?type=bug", theActiveProject: projects.Second);

        Assert.EndsWith(
            BoardFilterAddress.Of(projects.Second, BoardFilter.Everything with { Type = "bug" }),
            TheAddress(),
            StringComparison.Ordinal);
        Assert.True(TheLastNavigationReplacedItsHistoryEntry());
        Assert.Equal(["The second epic", "Held bug in the second"], TheTitles(board));
    }

    [Fact]
    public void AsksThePersonToPickAProjectWhenNeitherTheAddressNorTheTabNamesOne()
    {
        var board = TheBoardAt(BoardFilterAddress.Page, theActiveProject: null);

        Assert.Contains(NoActiveProject.Ask, board.Markup, StringComparison.Ordinal);
        Assert.Empty(TheTitles(board));
        Assert.EndsWith(BoardFilterAddress.Page, TheAddress(), StringComparison.Ordinal);
    }

    [Fact]
    public void SaysThatTheProjectOfItsAddressLeftTheRegistryAndShowsTheBoardOfNoOtherProject()
    {
        projects.Forget(projects.Second);

        var board = TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: projects.First);

        Assert.Equal(
            $"second is not in the registry any more, {TheBoardWords}",
            board.Find("p.board-message").TextContent);
        Assert.Empty(board.FindAll("table.board-table"));
        Assert.Empty(TheTitles(board));
    }

    [Fact]
    public void SaysThatTheAddressNamesNoProjectItCanReadAndShowsTheBoardOfNoOtherProject()
    {
        var board = TheBoardAt("board?project=garbage", theActiveProject: projects.Second);

        Assert.Equal($"garbage is no project path, {TheBoardWords}", board.Find("p.board-message").TextContent);
        Assert.Empty(board.FindAll("table.board-table"));
    }

    [Fact]
    public void NamesTheSameProjectInTheAddressThatAChangeInTheFilterBarWalksTo()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: null);

        board.Find("#filter-type").Change("bug");

        Assert.EndsWith(
            BoardFilterAddress.Of(projects.Second, BoardFilter.Everything with { Type = "bug" }),
            TheAddress(),
            StringComparison.Ordinal);
        Assert.False(TheLastNavigationReplacedItsHistoryEntry());
    }

    [Fact]
    public void NamesTheSameProjectInTheAddressThatATextSearchReplaces()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: null);

        board.Find("#filter-text").Input("loose");

        Assert.EndsWith(
            BoardFilterAddress.Of(projects.Second, BoardFilter.Everything with { Text = "loose" }),
            TheAddress(),
            StringComparison.Ordinal);
        Assert.True(TheLastNavigationReplacedItsHistoryEntry());
        Assert.Equal(["Loose in the second"], TheTitles(board));
    }

    [Fact]
    public void NamesTheSameProjectInTheAddressThatASavedFilterWalksTo()
    {
        var bugs = BoardFilter.Everything with { Type = "bug" };
        new SavedFilterCatalog(projects.Store).Save(projects.Second, "Bugs", bugs);
        var board = TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: null);

        board.FindAll("button").Single(button => button.TextContent == "Bugs").Click();

        Assert.EndsWith(BoardFilterAddress.Of(projects.Second, bugs), TheAddress(), StringComparison.Ordinal);
    }

    [Fact]
    public void DropsTheSelectionAndTheCollapsedRowsWhenTheAddressNamesAnotherProject()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.First), theActiveProject: null);
        board.FindAll("input[title='Select this bead']").Last().Change(true);
        board.Find("button.board-collapse").Click();
        Assert.Equal(["The first epic", "Loose in the first"], TheTitles(board));

        Navigation.NavigateTo(TheBoardAddressOf(projects.Second));

        board.WaitForAssertion(() => Assert.Equal(
            ["The second epic", "Held bug in the second", "Loose in the second"],
            TheTitles(board)));
        Assert.DoesNotContain(
            board.FindAll("input[type='checkbox']"),
            box => box.HasAttribute("checked"));
        Assert.Equal(projects.Second, projects.Selection.Current);
    }

    [Fact]
    public void DropsTheFilterOfTheOldProjectWhenTheAddressNamesAnotherProject()
    {
        var board = TheBoardAt(
            BoardFilterAddress.Of(projects.First, BoardFilter.Everything with { Type = "epic" }),
            theActiveProject: null);

        Navigation.NavigateTo(TheBoardAddressOf(projects.Second));

        board.WaitForAssertion(() => Assert.Equal(
            ["The second epic", "Held bug in the second", "Loose in the second"],
            TheTitles(board)));
        Assert.Equal(string.Empty, board.Find("#filter-type").GetAttribute("value"));
    }

    [Fact]
    public void ShowsTheFilterOfAnAddressThatNamesAnotherProject()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.First), theActiveProject: null);
        var bugsOfTheSecond = BoardFilterAddress.Of(projects.Second, BoardFilter.Everything with { Type = "bug" });

        Navigation.NavigateTo(bugsOfTheSecond);

        board.WaitForAssertion(() => Assert.Equal(["The second epic", "Held bug in the second"], TheTitles(board)));
        Assert.EndsWith(bugsOfTheSecond, TheAddress(), StringComparison.Ordinal);
    }

    [Fact]
    public void OffersTheSavedFiltersOfTheProjectThatTheNewAddressNames()
    {
        var catalog = new SavedFilterCatalog(projects.Store);
        catalog.Save(projects.First, "Epics of the first", BoardFilter.Everything with { Type = "epic" });
        catalog.Save(projects.Second, "Bugs of the second", BoardFilter.Everything with { Type = "bug" });
        var board = TheBoardAt(TheBoardAddressOf(projects.First), theActiveProject: null);

        Navigation.NavigateTo(TheBoardAddressOf(projects.Second));

        board.WaitForAssertion(() => Assert.Contains("Bugs of the second", board.Markup, StringComparison.Ordinal));
        Assert.DoesNotContain("Epics of the first", board.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void NamesTheProjectOnTheScreenInAnAddressThatNamesNoneAndKeepsTheSelection()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: null);
        board.FindAll("input[title='Select this bead']").Last().Change(true);

        Navigation.NavigateTo("board?type=task");

        board.WaitForAssertion(() => Assert.EndsWith(
            BoardFilterAddress.Of(projects.Second, BoardFilter.Everything with { Type = "task" }),
            TheAddress(),
            StringComparison.Ordinal));
        Assert.True(TheLastNavigationReplacedItsHistoryEntry());
        Assert.Equal(["Loose in the second"], TheTitles(board));
        Assert.True(board.Find("input[title='Select this bead']").HasAttribute("checked"));
    }

    [Fact]
    public void ReadsTheBeadsOnceForEachAddressThatWalksBetweenTheBoardsOfTwoProjects()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.First), theActiveProject: null);

        Navigation.NavigateTo(TheBoardAddressOf(projects.Second));
        board.WaitForAssertion(() => Assert.Equal(
            ["The second epic", "Held bug in the second", "Loose in the second"],
            TheTitles(board)));

        // The cache would answer the walk back without bd, so dropping it makes that walk read too.
        projects.Backlogs.Invalidate(projects.First);
        Navigation.NavigateTo(TheBoardAddressOf(projects.First));
        board.WaitForAssertion(() => Assert.Equal(
            ["The first epic", "Held in the first", "Loose in the first"],
            TheTitles(board)));

        Assert.Equal(2, projects.Bd.Runs(projects.First.Value, TheReadOfTheBeads));
        Assert.Equal(1, projects.Bd.Runs(projects.Second.Value, TheReadOfTheBeads));
        Assert.Equal(projects.First, projects.Selection.Current);
    }

    [Fact]
    public async Task DrawsNoBeadOfTheProjectThatTheBoardLeftWhenBdAnswersItsFirstReadLate()
    {
        projects.Bd.HoldsIn(projects.First.Value, ListCommand);
        projects.Bd.HoldsIn(projects.Second.Value, ListCommand);
        var board = TheBoardAt(TheBoardAddressOf(projects.First), theActiveProject: null);
        Navigation.NavigateTo(TheBoardAddressOf(projects.Second));

        projects.Bd.AnswersIn(projects.First.Value, ListCommand, TheBeadsOfTheFirstProject);
        await projects.Bd.StartsIn(projects.Second.Value, ListCommand).WaitAsync(Signals.LongEnough);
        Assert.Empty(TheTitles(board));

        projects.Bd.AnswersIn(projects.Second.Value, ListCommand, TheBeadsOfTheSecondProject);
        board.WaitForAssertion(() => Assert.Equal(
            ["The second epic", "Held bug in the second", "Loose in the second"],
            TheTitles(board)));
        Assert.EndsWith(TheBoardAddressOf(projects.Second), TheAddress(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task ShowsTheBeadsOfTheNewProjectAndNoWordOfTheOldOneWhenARereadOfTheProjectThatTheBoardLeftThrows()
    {
        var board = await TheBoardOfTheFirstProjectWhileARereadOfItWaits();

        Navigation.NavigateTo(TheBoardAddressOf(projects.Second));
        Assert.Empty(TheTitles(board));
        projects.Bd.ThrowsIn(projects.First.Value, ListCommand, "the pipe to bd closed");

        board.WaitForAssertion(() => Assert.Equal(
            ["The second epic", "Held bug in the second", "Loose in the second"],
            TheTitles(board)));
        Assert.Empty(board.FindAll(".board-message"));
        Assert.DoesNotContain("the pipe to bd closed", board.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public async Task SaysWhyOnTheBoardOfTheActiveProjectWhenARereadOfItThrows()
    {
        var board = await TheBoardOfTheFirstProjectWhileARereadOfItWaits();

        projects.Bd.ThrowsIn(projects.First.Value, ListCommand, "the pipe to bd closed");

        board.WaitForAssertion(() => Assert.Contains(
            "the pipe to bd closed",
            board.Find(".board-message").TextContent,
            StringComparison.Ordinal));
        Assert.Equal(["The first epic", "Held in the first", "Loose in the first"], TheTitles(board));
    }

    [Fact]
    public void ShowsTheBeadsThatAChangeDuringTheFirstReadOfTheBoardLeftBehind()
    {
        projects.Bd.HoldsIn(projects.First.Value, ListCommand);
        var board = TheBoardAt(TheBoardAddressOf(projects.First), theActiveProject: null);
        projects.Bd.PrintsIn(projects.First.Value, ListCommand, TheBeadsOfTheFirstProjectAfterAChange);

        projects.Backlogs.InvalidateFromWatch(projects.First);
        projects.Bd.AnswersIn(projects.First.Value, ListCommand, TheBeadsOfTheFirstProject);

        board.WaitForAssertion(() => Assert.Equal(
            ["The first epic", "Held in the first", "Loose in the first", "New in the first"],
            TheTitles(board)));
        Assert.Equal(2, projects.Bd.Runs(projects.First.Value, TheReadOfTheBeads));
    }

    [Fact]
    public void AsksBdForNothingWhenAPressOrATextSearchChangesOnlyTheFilterOfTheAddress()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: null);

        board.Find("#filter-type").Change("task");
        board.Find("#filter-text").Input("loose");

        Assert.Equal(["Loose in the second"], TheTitles(board));
        Assert.Equal(1, projects.Bd.Runs(projects.Second.Value, TheReadOfTheBeads));
    }

    [Fact]
    public void ReadsTheBeadsOnceWhenItNamesTheProjectOfTheTabInAnAddressThatNamesNone()
    {
        var board = TheBoardAt("board?type=bug", theActiveProject: projects.Second);

        Assert.Equal(["The second epic", "Held bug in the second"], TheTitles(board));
        Assert.Equal(1, projects.Bd.Runs(projects.Second.Value, TheReadOfTheBeads));
    }

    [Fact]
    public void WalksToTheBoardOfThePickedProjectWithNoFilterAsANewHistoryEntry()
    {
        var board = TheBoardAt(
            BoardFilterAddress.Of(projects.Second, BoardFilter.Everything with { Type = "bug" }),
            theActiveProject: null);

        APick.Of(this, projects.First);

        board.WaitForAssertion(() => Assert.Equal(
            ["The first epic", "Held in the first", "Loose in the first"],
            TheTitles(board)));
        Assert.EndsWith(TheBoardAddressOf(projects.First), TheAddress(), StringComparison.Ordinal);
        Assert.False(TheLastNavigationReplacedItsHistoryEntry());
    }

    [Fact]
    public void CallsTheBrowserForNothingWhenAPickWalksTheBoardToAnotherProject()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: null);

        APick.Of(this, projects.First);

        board.WaitForAssertion(() => Assert.Contains("The first epic", TheTitles(board)));
        Assert.Empty(JSInterop.Invocations);
    }

    [Theory]
    [InlineData("needs-you")]
    [InlineData("")]
    public void LeavesTheAddressOfTheNextPageAloneWhenAPersonWalksAwayFromTheBoard(string nextPage)
    {
        TheBoardAt(TheBoardAddressOf(projects.Second), theActiveProject: null);

        Navigation.NavigateTo(nextPage);

        Assert.Equal(nextPage, Navigation.ToBaseRelativePath(TheAddress()));
    }

    private static string TheBoardAddressOf(ProjectPath project) =>
        BoardFilterAddress.Of(project, BoardFilter.Everything);

    private static IReadOnlyList<string> TheTitles(IRenderedComponent<BoardPage> board) =>
        [.. board.FindAll("a.board-title").Select(title => title.TextContent)];

    private NavigationManager Navigation => Services.GetRequiredService<NavigationManager>();

    private string TheAddress() => Navigation.Uri;

    private bool TheLastNavigationReplacedItsHistoryEntry() =>
        Navigation is BunitNavigationManager navigation
        && navigation.History.First().Options.ReplaceHistoryEntry;

    // The board at this address, in a tab that holds this project or no project at all. The two
    // projects list other beads, so the titles on the board say which project it read.
    private async Task<IRenderedComponent<BoardPage>> TheBoardOfTheFirstProjectWhileARereadOfItWaits()
    {
        var board = TheBoardAt(TheBoardAddressOf(projects.First), theActiveProject: null);
        projects.Bd.HoldsIn(projects.First.Value, ListCommand);
        projects.Backlogs.Invalidate(projects.First);
        await projects.Bd.StartsIn(projects.First.Value, ListCommand).WaitAsync(Signals.LongEnough);
        return board;
    }

    private IRenderedComponent<BoardPage> TheBoardAt(string address, ProjectPath? theActiveProject)
    {
        projects.Bd
            .PrintsIn(projects.First.Value, ListCommand, TheBeadsOfTheFirstProject)
            .PrintsIn(projects.Second.Value, ListCommand, TheBeadsOfTheSecondProject);
        if (theActiveProject is not null)
        {
            projects.Selection.Select(theActiveProject);
        }

        projects.RegisterOn(Services);
        Services.AddSingleton(new SavedFilterCatalog(projects.Store));
        Services.AddSingleton(new BulkWriter(projects.Adapter));

        Navigation.NavigateTo(address);

        return Render<BoardPage>();
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
