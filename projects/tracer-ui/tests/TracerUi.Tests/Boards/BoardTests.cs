using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BoardTests
{
    private static readonly BoardFilter Default = BoardFilter.Everything;

    private static Backlog Of(params Bead[] beads) =>
        new(beads, [], new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal));

    [Fact]
    public void DrawsAnEpicAsARowWithTheBeadsItHoldsIndentedUnderIt()
    {
        var backlog = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "First") with { ParentId = "x" });

        var board = backlog.ToBoard(Default);

        Assert.Equal(["The epic", "First"], board.Rows.Select(row => row.Bead.Title));
        Assert.Equal([0, 1], board.Rows.Select(row => row.Depth));
    }

    [Fact]
    public void NestsASubEpicOneStepDeeperThanTheEpicThatHoldsIt()
    {
        var backlog = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" });

        var board = backlog.ToBoard(Default);

        Assert.Equal(
            ["The outer epic", "The inner epic", "Held deep"],
            board.Rows.Select(row => row.Bead.Title));
        Assert.Equal([0, 1, 2], board.Rows.Select(row => row.Depth));
    }

    [Fact]
    public void PutsABeadThatNoEpicHoldsUnderTheUnparentedRow()
    {
        var backlog = Of(ABead.Called("x-1", "Alone"));

        var board = backlog.ToBoard(Default);

        Assert.Empty(board.Rows);
        Assert.Equal(["Alone"], board.Unparented.Select(row => row.Bead.Title));
    }

    [Fact]
    public void PutsABeadWhoseNamedEpicIsNotInTheBacklogUnderTheUnparentedRow()
    {
        var backlog = Of(ABead.Called("x-1", "Stray") with { ParentId = "gone" });

        var board = backlog.ToBoard(Default);

        Assert.Empty(board.Rows);
        Assert.Equal(["Stray"], board.Unparented.Select(row => row.Bead.Title));
    }

    [Fact]
    public void KeepsAnEpicOnTheBoardWhenItHoldsNoBead()
    {
        var backlog = Of(ABead.Epic("x", "The empty epic"), ABead.Called("x-1", "Alone"));

        var board = backlog.ToBoard(Default);

        Assert.Equal(["The empty epic"], board.Rows.Select(row => row.Bead.Title));
        Assert.Equal(["Alone"], board.Unparented.Select(row => row.Bead.Title));
    }

    [Fact]
    public void KeepsAnEpicRowWhenTheFilterKeepsOnlyABeadBelowIt()
    {
        var backlog = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "A bug") with { ParentId = "inner", Type = "bug" },
            ABead.Called("x-2", "A task") with { ParentId = "inner" });

        var board = backlog.ToBoard(Default with { Type = "bug" });

        Assert.Equal(
            ["The outer epic", "The inner epic", "A bug"],
            board.Rows.Select(row => row.Bead.Title));
    }

    [Fact]
    public void LeavesOutAnEpicWhenTheFilterKeepsNeitherItNorAnyBeadBelowIt()
    {
        var backlog = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "A task") with { ParentId = "x" },
            ABead.Called("x-2", "A bug") with { Type = "bug" });

        var board = backlog.ToBoard(Default with { Type = "bug" });

        Assert.Empty(board.Rows);
        Assert.Equal(["A bug"], board.Unparented.Select(row => row.Bead.Title));
    }

    [Fact]
    public void KeepsAnEpicThatHoldsNoBeadWhenTheFilterNamesThatEpic()
    {
        var backlog = Of(ABead.Epic("x", "The empty epic"), ABead.Called("x-1", "Elsewhere"));

        var board = backlog.ToBoard(Default with { Epic = "x" });

        Assert.Equal(["The empty epic"], board.Rows.Select(row => row.Bead.Title));
        Assert.Empty(board.Unparented);
    }

    [Fact]
    public void KeepsAClosedEpicThatHoldsAShownBeadAndSaysThatItIsClosed()
    {
        var backlog = Of(
            ABead.Epic("x", "The closed epic") with { Status = "closed" },
            ABead.Called("x-1", "Still open") with { ParentId = "x" });

        var board = backlog.ToBoard(Default);

        Assert.Equal(["The closed epic", "Still open"], board.Rows.Select(row => row.Bead.Title));
        Assert.Equal("closed", board.Rows[0].Status.Text);
    }

    [Fact]
    public void PutsTheBeadsOfTheUnparentedRowAfterTheWholeTree()
    {
        var backlog = Of(
            ABead.Called("x-1", "Alone"),
            ABead.Epic("x", "The epic"),
            ABead.Called("x-2", "Held") with { ParentId = "x" });

        Assert.Equal(["The epic", "Held", "Alone"], Titles(backlog, Default));
    }

    [Fact]
    public void ShowsTheOpenAndTheInProgressBeadsAndHidesTheDeferredAndTheClosedOnes()
    {
        var backlog = Of(
            ABead.Called("x-1", "Open"),
            ABead.Called("x-2", "Claimed") with { Status = "in_progress" },
            ABead.Called("x-3", "Put off") with { Status = "deferred" },
            ABead.Called("x-4", "Done") with { Status = "closed" });

        Assert.Equal(["Claimed", "Open"], Titles(backlog, Default));
    }

    [Fact]
    public void BringsTheDeferredBeadsIntoViewWhenTheDeferredToggleIsOn()
    {
        var backlog = Of(
            ABead.Called("x-1", "Open"),
            ABead.Called("x-3", "Put off") with { Status = "deferred" },
            ABead.Called("x-4", "Done") with { Status = "closed" });

        Assert.Equal(
            ["Open", "Put off"],
            Titles(backlog, Default with { ShowDeferred = true, ShowClosed = false }));
    }

    [Fact]
    public void BringsTheClosedBeadsIntoViewWithTheirCloseReasonWhenTheClosedToggleIsOn()
    {
        var backlog = Of(
            ABead.Called("x-1", "Open"),
            ABead.Called("x-4", "Done") with { Status = "closed", CloseReason = "the toggle showed nothing worth keeping open" });

        var board = backlog.ToBoard(Default with { ShowDeferred = false, ShowClosed = true });
        var done = board.EveryRow.Single(row => row.Bead.Title == "Done");
        Assert.Equal("the toggle showed nothing worth keeping open", done.Bead.CloseReason);
    }

    [Fact]
    public void OrdersTheReadyBeadsFirstThenByPriorityThenByTitle()
    {
        var backlog = new Backlog(
            [
                ABead.Called("x-1", "Zebra") with { Priority = 3 },
                ABead.Called("x-2", "Alpha") with { Priority = 3 },
                ABead.Called("x-3", "Urgent") with { Priority = 0 },
                ABead.Called("x-4", "Ready one") with { Priority = 4 },
            ],
            ["x-4"],
            new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal));

        Assert.Equal(
            ["Ready one", "Urgent", "Alpha", "Zebra"],
            Titles(backlog, Default));
    }

    [Fact]
    public void OrdersTheBeadsUnderOneEpicByTheSameRuleAsTheEpicsThemselves()
    {
        var backlog = new Backlog(
            [
                ABead.Epic("late", "The late epic") with { Priority = 3 },
                ABead.Epic("early", "The early epic") with { Priority = 1 },
                ABead.Called("x-1", "Zebra") with { ParentId = "early", Priority = 3 },
                ABead.Called("x-2", "Alpha") with { ParentId = "early", Priority = 3 },
                ABead.Called("x-3", "Ready one") with { ParentId = "early", Priority = 4 },
            ],
            ["x-3"],
            new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal));

        Assert.Equal(
            ["The early epic", "Ready one", "Alpha", "Zebra", "The late epic"],
            Titles(backlog, Default));
    }

    [Fact]
    public void DrawsABeadOfACycleAmongEpicsOnceAndAtTheTopOfTheTree()
    {
        var backlog = Of(
            ABead.Epic("one", "The first epic") with { ParentId = "two" },
            ABead.Epic("two", "The second epic") with { ParentId = "one" },
            ABead.Called("x-1", "Held") with { ParentId = "one" });

        var board = backlog.ToBoard(Default);

        Assert.Equal(
            ["The first epic", "Held", "The second epic"],
            board.Rows.Select(row => row.Bead.Title));
        Assert.Equal([0, 1, 0], board.Rows.Select(row => row.Depth));
    }

    [Fact]
    public void ResolvesTheStatusOfEveryRowItShows()
    {
        var backlog = new Backlog(
            [ABead.Called("x-1", "First")],
            ["x-1"],
            new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal));

        var row = Assert.Single(backlog.ToBoard(Default).Unparented);
        Assert.Equal("ready", row.Status.Text);
    }

    [Fact]
    public void HidesABeadInAStatusThatNeitherTheDefaultViewNorAToggleNames()
    {
        var backlog = Of(ABead.Called("x-1", "Open"), ABead.Called("x-2", "Odd") with { Status = "archived" });

        Assert.Equal(["Open"], Titles(backlog, Default with { ShowDeferred = true, ShowClosed = true }));
    }

    [Fact]
    public void KeepsOnlyTheRowsThatTheFilterMatches()
    {
        var backlog = Of(
            ABead.Called("x-1", "A bug") with { Type = "bug" },
            ABead.Called("x-2", "A task") with { Type = "task" });

        Assert.Equal(["A bug"], Titles(backlog, Default with { Type = "bug" }));
    }

    [Fact]
    public void ShowsTheStatusThatTheFilterNamesWithoutAToggleForIt()
    {
        var backlog = Of(
            ABead.Called("x-1", "Open"),
            ABead.Called("x-2", "Done") with { Status = "closed" });

        Assert.Equal(["Done"], Titles(backlog, Default with { Status = "closed" }));
    }

    [Fact]
    public void NamesEveryTypeThatABeadUsesOnceAndInOrder()
    {
        var backlog = Of(
            ABead.Called("x-1", "Second") with { Type = "task" },
            ABead.Called("x-2", "First") with { Type = "bug" },
            ABead.Called("x-3", "Third") with { Type = "task" });

        Assert.Equal(["bug", "task"], backlog.Types);
    }

    [Fact]
    public void NamesEveryPriorityThatABeadStatesOnceAndFromTheMostUrgent()
    {
        var backlog = Of(
            ABead.Called("x-1", "First") with { Priority = 2 },
            ABead.Called("x-2", "Second") with { Priority = 0 },
            ABead.Called("x-3", "Third") with { Priority = 2 },
            ABead.Called("x-4", "Fourth") with { Priority = Bead.NoPriority });

        Assert.Equal([0, 2], backlog.Priorities);
    }

    [Fact]
    public void NamesEveryLabelThatABeadCarriesOnceAndInOrder()
    {
        var backlog = Of(
            ABead.Called("x-1", "First") with { Labels = ["ui", "human"] },
            ABead.Called("x-2", "Second") with { Labels = ["human"] });

        Assert.Equal(["human", "ui"], backlog.Labels);
    }

    [Fact]
    public void NamesEveryEpicOfTheBacklogWhetherOrNotItHoldsAShownBead()
    {
        var backlog = Of(
            ABead.Epic("x", "The epic"),
            ABead.Epic("y", "The empty epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" });

        Assert.Equal(["The epic", "The empty epic"], backlog.Epics.Select(epic => epic.Title));
    }

    [Fact]
    public void KeepsTheBeadsOfASubEpicWhenTheFilterNamesTheEpicAboveIt()
    {
        var backlog = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" },
            ABead.Called("x-2", "Elsewhere"));

        Assert.Equal(
            ["The outer epic", "The inner epic", "Held deep"],
            Titles(backlog, Default with { Epic = "outer" }));
    }

    [Fact]
    public void NamesTheEpicsAboveABeadFromTheOneThatHoldsItOutward()
    {
        var backlog = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" });

        Assert.Equal(["inner", "outer"], backlog.EpicsAbove(ABead.Called("x-1", "Held deep") with { ParentId = "inner" }));
    }

    [Fact]
    public void EndsTheWalkUpTheEpicsWhenTheEpicsFormACycle()
    {
        var backlog = Of(
            ABead.Epic("one", "The first epic") with { ParentId = "two" },
            ABead.Epic("two", "The second epic") with { ParentId = "one" },
            ABead.Called("x-1", "Held") with { ParentId = "one" });

        Assert.Equal(["one", "two"], backlog.EpicsAbove(ABead.Called("x-1", "Held") with { ParentId = "one" }));
    }

    [Fact]
    public void CountsTwoSpellingsOfOneTypeOrOneLabelThatDifferOnlyInCaseAsOne()
    {
        var backlog = Of(
            ABead.Called("x-1", "First") with { Type = "Bug", Labels = ["Human"] },
            ABead.Called("x-2", "Second") with { Type = "bug", Labels = ["human"] });

        Assert.Single(backlog.Types);
        Assert.Single(backlog.Labels);
    }

    [Fact]
    public void GivesAnEpicRowTheIdOfEveryBeadBelowItAtAnyDepth()
    {
        var backlog = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" });

        var board = backlog.ToBoard(Default);

        Assert.Equal(["outer", "inner", "x-1"], board.Rows[0].Branch);
    }

    [Fact]
    public void GivesARowThatHoldsNoBeadItsOwnIdAlone()
    {
        var backlog = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" },
            ABead.Called("x-2", "Alone"));

        var board = backlog.ToBoard(Default);

        Assert.Equal(["x-1"], board.Rows[1].Branch);
        Assert.Equal(["x-2"], board.Unparented[0].Branch);
    }

    [Fact]
    public void LeavesOutOfABranchABeadThatTheFilterHides()
    {
        var backlog = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "A bug") with { ParentId = "x", Type = "bug" },
            ABead.Called("x-2", "A task") with { ParentId = "x" });

        var board = backlog.ToBoard(Default with { Type = "bug" });

        Assert.Equal(["x", "x-1"], board.Rows[0].Branch);
    }

    [Fact]
    public void TakesAWholeBranchIntoASelectionAndNoBeadBesideIt()
    {
        var backlog = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" },
            ABead.Called("x-2", "Elsewhere"));
        var selection = new IdSet();

        selection.ToggleAll(backlog.ToBoard(Default).Rows[0].Branch);

        Assert.True(selection.HoldsAll(["outer", "inner", "x-1"]));
        Assert.Equal(3, selection.Count);
    }

    [Fact]
    public void SaysHowManyBeadsAnEpicRowHoldsAtAnyDepth()
    {
        var backlog = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" });

        var board = backlog.ToBoard(Default);

        Assert.Equal([2, 1, 0], board.Rows.Select(row => row.Held));
    }

    [Fact]
    public void LeavesOutOfTheCountOfARowABeadThatTheFilterHides()
    {
        var backlog = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "A bug") with { ParentId = "x", Type = "bug" },
            ABead.Called("x-2", "A task") with { ParentId = "x" },
            ABead.Called("x-3", "Another task") with { ParentId = "x" });

        var board = backlog.ToBoard(Default with { Type = "bug" });

        Assert.Equal(1, board.Rows[0].Held);
    }

    [Fact]
    public void SaysHowManyBeadsGatherUnderTheUnparentedRowAndCountsOnlyTheOnesTheFilterKeeps()
    {
        var backlog = Of(
            ABead.Called("x-1", "A bug") with { Type = "bug" },
            ABead.Called("x-2", "A task"),
            ABead.Called("x-3", "Another task"));

        Assert.Equal(3, backlog.ToBoard(Default).UnparentedHeld);
        Assert.Equal(1, backlog.ToBoard(Default with { Type = "bug" }).UnparentedHeld);
    }

    private static IEnumerable<string> Titles(Backlog backlog, BoardFilter filter) =>
        backlog.ToBoard(filter).EveryRow.Select(row => row.Bead.Title);
}
