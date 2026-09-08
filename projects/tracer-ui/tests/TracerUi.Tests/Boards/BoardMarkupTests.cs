using Bunit;
using AngleSharp.Dom;
using AngleSharp.Html.Dom;
using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Look;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;
using TracerUi.Tests.Projects;
using TracerUi.Web.Components.Layout;
using TracerUi.Web.Components.Pages;
using BoardPage = TracerUi.Web.Components.Pages.Board;

namespace TracerUi.Tests.Boards;

/// <summary>The board as a browser draws it: the markup of one row, and what a press on it does.</summary>
public sealed class BoardMarkupTests : BunitContext
{
    private const string OneBead =
        """[{"id": "x-1", "title": "First", "issue_type": "task", "priority": 2, "status": "open"}]""";

    // One bead that states a Demo line, so no row of that board carries a no-demo marker.
    private const string OneBeadWithADemoLine =
        """
        [{"id": "x-1", "title": "First", "issue_type": "task", "priority": 2, "status": "open",
          "description": "## Demo\n\nRead the board."}]
        """;

    // Two beads that differ in every fact a press can set: the type, the priority, the labels and
    // the Demo line. A press on one of them therefore takes one bead off the board and keeps the
    // other.
    private const string TwoBeads =
        """
        [{"id": "x-1", "title": "First", "issue_type": "task", "priority": 2, "status": "open",
          "labels": ["ui"], "description": "## Demo\n\nRead the board."},
         {"id": "x-2", "title": "Second", "issue_type": "bug", "priority": 3, "status": "open",
          "labels": ["docs"]}]
        """;

    private readonly TempDirectory directory = new();

    [Fact]
    public void StaysOnTheBoardWhenAPressTravelsAcrossARowAndReleasesFarFromWhereItStarted()
    {
        var board = TheBoardOfOneBead();
        var where = ABrowser.TheAddressItStandsOn(this);

        APress.DragsAcross(TheRowOfTheOneBead(board), APress.Plain);

        Assert.Equal(where, ABrowser.TheAddressItStandsOn(this));
    }

    [Fact]
    public void OpensTheBeadWhenAPressReleasesWhereItStarted()
    {
        var board = TheBoardOfOneBead();

        APress.LandsOn(TheRowOfTheOneBead(board), APress.Plain);

        Assert.EndsWith("bead/x-1", ABrowser.TheAddressItStandsOn(this), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(NewTabKey.Meta)]
    [InlineData(NewTabKey.Control)]
    public void OpensTheBeadInANewTabWhenAPressOnARowCarriesAKeyThatAsksForOne(NewTabKey key)
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var board = TheBoardOfOneBead();

        APress.LandsOn(TheRowOfTheOneBead(board), TheReleaseThatCarries(key));

        Assert.Equal(["bead/x-1"], ABrowser.TheAddressesOf(opened));
    }

    [Theory]
    [InlineData(NewTabKey.Meta)]
    [InlineData(NewTabKey.Control)]
    public void StaysOnTheBoardWhenAPressOnARowAsksForANewTab(NewTabKey key)
    {
        ABrowser.ThatOpensEveryTab(this);
        var board = TheBoardOfOneBead();
        var where = ABrowser.TheAddressItStandsOn(this);

        APress.LandsOn(TheRowOfTheOneBead(board), TheReleaseThatCarries(key));

        Assert.Equal(where, ABrowser.TheAddressItStandsOn(this));
    }

    [Fact]
    public void OpensTheBeadInANewTabWhenTheMiddleButtonReleasesOnARow()
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var board = TheBoardOfOneBead();

        TheRowOfTheOneBead(board)().MouseUp(APress.OfTheMiddleButton);

        Assert.Equal(["bead/x-1"], ABrowser.TheAddressesOf(opened));
    }

    [Fact]
    public void OpensTheBeadInThisTabWhenTheTitleOfARowTakesAPlainPress()
    {
        var board = TheBoardOfOneBead();

        board.Find("a.board-title").Click(APress.Plain);

        Assert.EndsWith("bead/x-1", ABrowser.TheAddressItStandsOn(this), StringComparison.Ordinal);
    }

    [Fact]
    public void OpensOneTabAloneWhenAPressOnTheTitleOfARowAsksForANewTab()
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var board = TheBoardOfOneBead();

        board.Find("a.board-title").Click(TheReleaseThatCarries(NewTabKey.Meta));

        Assert.Equal(["bead/x-1"], ABrowser.TheAddressesOf(opened));
    }

    [Fact]
    public void OpensNoTabWhenAPressTravelsAcrossARowAndAsksForANewTab()
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var board = TheBoardOfOneBead();

        APress.DragsAcross(TheRowOfTheOneBead(board), APress.CarryingTheMetaKey);

        Assert.Empty(ABrowser.TheAddressesOf(opened));
    }

    [Fact]
    public void OpensTheBeadWhenAPressReachesTheRowFromTheCellThatHoldsTheId()
    {
        var board = TheBoardOfOneBead();

        board.Find("tr.board-row:not(.board-unparented) td.board-cell-quiet").Click();

        Assert.EndsWith("bead/x-1", ABrowser.TheAddressItStandsOn(this), StringComparison.Ordinal);
    }

    [Fact]
    public void KeepsOnlyTheBeadsOfATypeWhenThatTypePressesOnARow()
    {
        var board = TheBoardOf(TwoBeads);

        Follow(ThePress(board, "type", "bug"));

        Assert.Equal(["Second"], TheTitles(board));
    }

    [Fact]
    public void ShowsEveryBeadAgainWhenTheSameTypePressesASecondTime()
    {
        var board = TheBoardOf(TwoBeads);

        Follow(ThePress(board, "type", "bug"));
        Follow(ThePress(board, "type", "bug"));

        Assert.Equal(["First", "Second"], TheTitles(board));
    }

    [Fact]
    public void NamesTheBoardAndNoBeadInTheAddressOfAPress()
    {
        var board = TheBoardOf(TwoBeads);

        Assert.Equal("board?type=bug", TheAddressOf(ThePress(board, "type", "bug")));
    }

    [Fact]
    public void KeepsOnlyTheBeadsOfAPriorityWhenThatPriorityPressesOnARow()
    {
        var board = TheBoardOf(TwoBeads);

        Follow(ThePress(board, "priority", "p3"));

        Assert.Equal(["Second"], TheTitles(board));
    }

    [Fact]
    public void NamesThePriorityByItsNumberAloneInTheAddressOfAPress()
    {
        var board = TheBoardOf(TwoBeads);

        Assert.Equal("board?priority=3", TheAddressOf(ThePress(board, "priority", "p3")));
    }

    [Fact]
    public void ShowsThePriorityOfAPressInTheFilterBar()
    {
        var board = TheBoardOf(TwoBeads);

        Follow(ThePress(board, "priority", "p3"));

        Assert.Equal("3", ((IHtmlSelectElement)board.Find("#filter-priority")).Value);
    }

    [Fact]
    public void PressesNowhereOnThePriorityOfARowThatStatesNone()
    {
        var board = TheBoardOf(
            """[{"id": "x-1", "title": "First", "issue_type": "task", "status": "open"}]""");

        Assert.Empty(board.FindAll("a.board-filter-press-priority"));
    }

    [Fact]
    public void KeepsOnlyTheBeadsThatCarryALabelWhenThatLabelPressesOnARow()
    {
        var board = TheBoardOf(TwoBeads);

        Follow(ThePress(board, "label", "docs"));

        Assert.Equal(["Second"], TheTitles(board));
    }

    [Fact]
    public void KeepsOnlyTheBeadsWithNoDemoLineWhenThatMarkerPressesOnARow()
    {
        var board = TheBoardOf(TwoBeads);

        Follow(ThePress(board, "demo", "no demo"));

        Assert.Equal(["Second"], TheTitles(board));
    }

    [Fact]
    public void PressesNowhereOnTheMarkerOfARowThatStatesADemoLine()
    {
        var board = TheBoardOf(OneBeadWithADemoLine);

        Assert.Empty(board.FindAll("a.board-filter-press-demo"));
    }

    [Fact]
    public void ShowsTheTypeOfAPressInTheFilterBar()
    {
        var board = TheBoardOf(TwoBeads);

        Follow(ThePress(board, "type", "bug"));

        Assert.Equal("bug", ((IHtmlSelectElement)board.Find("#filter-type")).Value);
    }

    [Fact]
    public void PressesNowhereOnTheTypeOfARowThatNamesNoType()
    {
        var board = TheBoardOf(
            """[{"id": "x-1", "title": "First", "issue_type": "", "priority": 2, "status": "open"}]""");

        Assert.Empty(board.FindAll("a.board-filter-press-type"));
    }

    [Fact]
    public void SaysThatTheBrowserRefusedTheTabWhenAPressOnARowAsksForOneAndNoTabOpens()
    {
        var board = TheBoardOfOneBead();
        ABrowser.ThatRefusesEveryTab(this);

        APress.LandsOn(TheRowOfTheOneBead(board), TheReleaseThatCarries(NewTabKey.Meta));

        Assert.Contains("popups", TheNewTabRefusal.On(board));
    }

    [Fact]
    public void SaysNothingAboutANewTabWhenTheBrowserOpensTheOneThatARowAsksFor()
    {
        var board = TheBoardOfOneBead();
        ABrowser.ThatOpensEveryTab(this);

        APress.LandsOn(TheRowOfTheOneBead(board), TheReleaseThatCarries(NewTabKey.Meta));

        Assert.Empty(TheNewTabRefusal.EveryOneOn(board));
    }

    [Fact]
    public void StopsTheRefusalOfATabWhenALaterPressOnARowOpensOne()
    {
        var board = TheBoardOfOneBead();
        var browser = ABrowser.ThatRefusesEveryTab(this);
        APress.LandsOn(TheRowOfTheOneBead(board), TheReleaseThatCarries(NewTabKey.Meta));

        browser.SetResult(true);
        APress.LandsOn(TheRowOfTheOneBead(board), TheReleaseThatCarries(NewTabKey.Meta));

        Assert.Empty(TheNewTabRefusal.EveryOneOn(board));
    }

    [Fact]
    public void DrawsTheRowOfABeadAsAPressableRowThatHoldsTheTitleOfThatBead()
    {
        var board = TheBoardOfOneBead();

        Assert.Single(board.FindComponents<PressableRow>());
        Assert.Single(board.FindComponents<RowTitle>());
    }

    [Fact]
    public void OffersEveryTypeButTheEpicInTheQuickCreateOfTheBoard()
    {
        var board = TheBoardOfOneBead();

        Assert.Equal(
            AQuickCreate.TheTypesItOffersSpelledOut,
            AQuickCreate.TheTypesItOffers(board, "create-type"));
    }

    [Fact]
    public void LabelsTheTitleBoxAndTheTypePickerOfTheQuickCreateOfTheBoard()
    {
        var board = TheBoardOfOneBead();

        Assert.Equal("Capture a bead", AQuickCreate.TheLabelOf(board, "create-title"));
        Assert.Equal("Type", AQuickCreate.TheLabelOf(board, "create-type"));
    }

    [Fact]
    public void DrawsTheFieldsOfTheQuickCreateOfTheBoardFromTheComponentThatEverySurfaceShares()
    {
        var board = TheBoardOfOneBead();

        Assert.NotNull(AQuickCreate.TheFieldsOf(board));
    }

    [Fact]
    public void OffersTheEpicInsideTheSharedFieldsOfTheQuickCreateOfTheBoard()
    {
        var board = TheBoardOfOneBead();

        Assert.Single(AQuickCreate.TheFieldsOf(board).FindAll("#create-epic"));
    }

    // The modifier keys that ask a browser for a new tab on a link.
    public enum NewTabKey
    {
        Meta,
        Control,
    }

    private static MouseEventArgs TheReleaseThatCarries(NewTabKey key) =>
        key == NewTabKey.Meta ? APress.CarryingTheMetaKey : APress.CarryingTheControlKey;

    private const string OneBeadInEachStatus =
        """
        [{"id": "x-1", "title": "Needs you", "issue_type": "task", "priority": 0, "status": "open",
          "labels": ["human"]},
         {"id": "x-2", "title": "Ready", "issue_type": "task", "priority": 1, "status": "open"},
         {"id": "x-3", "title": "Blocked", "issue_type": "task", "priority": 2, "status": "open"},
         {"id": "x-4", "title": "Deferred", "issue_type": "task", "priority": 3, "status": "deferred"},
         {"id": "x-5", "title": "In progress", "issue_type": "task", "priority": 4,
          "status": "in_progress", "assignee": "claude"},
         {"id": "x-6", "title": "Stored", "issue_type": "task", "priority": 4, "status": "closed"}]
        """;

    [Fact]
    public void DrawsTheStatusPillOfEachRowInTheClassThatTheStylesheetColors()
    {
        var board = TheBoardOf(
            new ABacklog(
                OneBeadInEachStatus,
                Ready: """[{"id": "x-1"}, {"id": "x-2"}]""",
                Blocked: """[{"id": "x-3", "blocked_by": ["x-2"]}]"""),
            "board?deferred=true&closed=true");

        Assert.Equal(
            [
                "board-status-needs-you",
                "board-status-ready",
                "board-status-blocked",
                "board-status-deferred",
                "board-status-in-progress",
                "board-status-stored",
            ],
            TheStatusClasses(board));
    }

    private static IReadOnlyList<string> TheStatusClasses(IRenderedComponent<BoardPage> board) =>
        [.. board.FindAll("span.board-status")
            .Select(pill => pill.ClassList.Single(name =>
                name.StartsWith("board-status-", StringComparison.Ordinal)))];

    private static Func<IElement> TheRowOfTheOneBead(IRenderedComponent<BoardPage> board) =>
        () => board.Find("tr.board-row:not(.board-unparented)");

    private IRenderedComponent<BoardPage> TheBoardOfOneBead() =>
        TheBoardOf(OneBead, BoardFilterAddress.Page);

    private IRenderedComponent<BoardPage> TheBoardOf(string beads) =>
        TheBoardOf(beads, BoardFilterAddress.Page);

    [Fact]
    public void OpensOnTheFilterThatItsOwnAddressStates()
    {
        var board = TheBoardOf(TwoBeads, "board?type=bug");

        Assert.Equal(["Second"], TheTitles(board));
    }

    // Follows a filter press, as a browser follows the link that a press is. The test harness draws
    // the markup and follows no link of its own, so the test takes the address that the press names.
    private void Follow(IElement press) =>
        Services.GetRequiredService<NavigationManager>().NavigateTo(TheAddressOf(press));

    private static string TheAddressOf(IElement press) => press.GetAttribute("href") ?? string.Empty;

    // The filter press of one kind, on the row whose word it names. A press carries the word that a
    // person reads, so the test asks for it the way that person would.
    private static IElement ThePress(IRenderedComponent<BoardPage> board, string kind, string word) =>
        board.FindAll($"a.board-filter-press-{kind}").Single(press => press.TextContent == word);

    private static IReadOnlyList<string> TheTitles(IRenderedComponent<BoardPage> board) =>
        [.. board.FindAll("a.board-title").Select(title => title.TextContent)];

    // What bd answers about one backlog: the beads it lists, the ready ones, and the blocked ones
    // with what blocks them. A board reads all three, so they travel as one value.
    private sealed record ABacklog(string Beads, string Ready, string Blocked)
    {
        // A backlog where bd calls no bead ready and no bead blocked, so every row falls back to
        // the status that bd stored.
        public static ABacklog OfBeadsAlone(string beads) => new(beads, "[]", "[]");
    }

    // The board of these beads, as the browser draws it at this address. The address carries the
    // filter, so a test states the one that the board opens on.
    private IRenderedComponent<BoardPage> TheBoardOf(string beads, string address) =>
        TheBoardOf(ABacklog.OfBeadsAlone(beads), address);

    private IRenderedComponent<BoardPage> TheBoardOf(ABacklog backlog, string address)
    {
        var project = ProjectPath.From(directory.Path);
        var store = new InMemoryProjectRegistryStore();
        store.Save(new ProjectRegistry([project], []));

        var bd = new FakeBd()
            .Prints("list --all --limit 0 --json", backlog.Beads)
            .Prints("ready --json", backlog.Ready)
            .Prints("blocked --json", backlog.Blocked);
        var adapter = new BdAdapter(bd);
        var cache = new BacklogCache(new BacklogReader(adapter), adapter);
        var catalog = new ProjectCatalog(store, adapter);
        var selection = new ActiveProjectSelection(catalog);
        selection.Select(project);

        Services.AddSingleton(adapter);
        Services.AddSingleton(cache);
        Services.AddSingleton(new ProjectWatchers(cache));
        Services.AddSingleton(catalog);
        Services.AddSingleton(selection);
        Services.AddSingleton(new SavedFilterCatalog(store));
        Services.AddSingleton(new BulkWriter(adapter));
        Services.AddSingleton(new CopyFeedback());
        Services.AddScoped<BeadOpener>();

        Services.GetRequiredService<NavigationManager>().NavigateTo(address);

        return Render<BoardPage>();
    }

    protected override void Dispose(bool disposing)
    {
        directory.Dispose();
        base.Dispose(disposing);
    }
}
