using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class CollapsedRowsTests
{
    private static readonly BoardFilter Default = BoardFilter.Everything;

    private static Backlog Of(params Bead[] beads) =>
        new(beads, [], new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal));

    [Fact]
    public void HidesTheBeadsUnderAnEpicThatAPersonCollapsed()
    {
        var rows = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "First") with { ParentId = "x" }).ToBoard(Default).Rows;
        var collapsed = new CollapsedRows();

        collapsed.Toggle("x");

        Assert.Equal(["The epic"], collapsed.Draws(rows).Select(row => row.Bead.Title));
    }

    [Fact]
    public void HidesASubEpicAndTheBeadsUnderItWhenTheEpicAboveThemCollapses()
    {
        var rows = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" }).ToBoard(Default).Rows;
        var collapsed = new CollapsedRows();

        collapsed.Toggle("outer");

        Assert.Equal(["The outer epic"], collapsed.Draws(rows).Select(row => row.Bead.Title));
    }

    [Fact]
    public void DrawsEveryRowUntilAPersonCollapsesAnEpic()
    {
        var rows = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "First") with { ParentId = "x" }).ToBoard(Default).Rows;

        var drawn = new CollapsedRows().Draws(rows);

        Assert.Equal(["The epic", "First"], drawn.Select(row => row.Bead.Title));
    }

    [Fact]
    public void DrawsTheBeadsUnderAnEpicAgainAfterASecondPress()
    {
        var rows = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "First") with { ParentId = "x" }).ToBoard(Default).Rows;
        var collapsed = new CollapsedRows();

        collapsed.Toggle("x");
        collapsed.Toggle("x");

        Assert.Equal(["The epic", "First"], collapsed.Draws(rows).Select(row => row.Bead.Title));
    }

    [Fact]
    public void KeepsTheBeadsOfEveryOtherEpicOnTheBoard()
    {
        var rows = Of(
            ABead.Epic("x", "The first epic"),
            ABead.Called("x-1", "Hidden") with { ParentId = "x" },
            ABead.Epic("y", "The second epic"),
            ABead.Called("y-1", "Shown") with { ParentId = "y" }).ToBoard(Default).Rows;
        var collapsed = new CollapsedRows();

        collapsed.Toggle("x");

        Assert.Equal(
            ["The first epic", "The second epic", "Shown"],
            collapsed.Draws(rows).Select(row => row.Bead.Title));
    }

    [Fact]
    public void SaysWhichEpicsItHoldsSoThatARowDrawsTheControlOfItsOwnState()
    {
        var collapsed = new CollapsedRows();

        collapsed.Toggle("x");

        Assert.True(collapsed.Holds("x"));
        Assert.False(collapsed.Holds("y"));
    }

    [Fact]
    public void OpensEveryEpicAgainWhenTheBoardMovesToAnotherProject()
    {
        var rows = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "First") with { ParentId = "x" }).ToBoard(Default).Rows;
        var collapsed = new CollapsedRows();
        collapsed.Toggle("x");

        collapsed.OpenAll();

        Assert.Equal(["The epic", "First"], collapsed.Draws(rows).Select(row => row.Bead.Title));
    }

    [Fact]
    public void HidesTheLooseBeadsWhenAPersonCollapsesTheUnparentedRow()
    {
        var unparented = Of(ABead.Called("x-1", "Loose")).ToBoard(Default).Unparented;
        var collapsed = new CollapsedRows();

        collapsed.ToggleUnparented();

        Assert.Empty(collapsed.DrawsUnparented(unparented));
    }

    [Fact]
    public void OpensTheUnparentedRowAgainWhenTheBoardMovesToAnotherProject()
    {
        var unparented = Of(ABead.Called("x-1", "Loose")).ToBoard(Default).Unparented;
        var collapsed = new CollapsedRows();
        collapsed.ToggleUnparented();

        collapsed.OpenAll();

        Assert.Equal(["Loose"], collapsed.DrawsUnparented(unparented).Select(row => row.Bead.Title));
    }

    [Fact]
    public void DrawsTheLooseBeadsUntilAPersonCollapsesTheUnparentedRow()
    {
        var unparented = Of(ABead.Called("x-1", "Loose")).ToBoard(Default).Unparented;

        var drawn = new CollapsedRows().DrawsUnparented(unparented);

        Assert.Equal(["Loose"], drawn.Select(row => row.Bead.Title));
    }

    [Fact]
    public void DrawsTheLooseBeadsAgainAfterASecondPressOnTheUnparentedRow()
    {
        var unparented = Of(ABead.Called("x-1", "Loose")).ToBoard(Default).Unparented;
        var collapsed = new CollapsedRows();

        collapsed.ToggleUnparented();
        collapsed.ToggleUnparented();

        Assert.Equal(["Loose"], collapsed.DrawsUnparented(unparented).Select(row => row.Bead.Title));
    }

    [Fact]
    public void SaysThatItHoldsTheUnparentedRowSoThatTheRowDrawsTheControlOfItsOwnState()
    {
        var collapsed = new CollapsedRows();

        Assert.False(collapsed.HoldsUnparented);

        collapsed.ToggleUnparented();

        Assert.True(collapsed.HoldsUnparented);
    }

    [Fact]
    public void KeepsTheTreeOnTheBoardWhenAPersonCollapsesTheUnparentedRow()
    {
        var board = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" },
            ABead.Called("x-2", "Loose")).ToBoard(Default);
        var collapsed = new CollapsedRows();

        collapsed.ToggleUnparented();

        Assert.Equal(["The epic", "Held"], collapsed.Draws(board.Rows).Select(row => row.Bead.Title));
        Assert.Empty(collapsed.DrawsUnparented(board.Unparented));
    }

    [Fact]
    public void KeepsTheLooseBeadsOnTheBoardWhenAPersonCollapsesAnEpic()
    {
        var board = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" },
            ABead.Called("x-2", "Loose")).ToBoard(Default);
        var collapsed = new CollapsedRows();

        collapsed.Toggle("x");

        Assert.Equal(["Loose"], collapsed.DrawsUnparented(board.Unparented).Select(row => row.Bead.Title));
    }

    [Fact]
    public void LeavesOnlyTheRowsThatHeadTheBoardWhenAPersonCollapsesAll()
    {
        var board = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" },
            ABead.Epic("y", "The second epic"),
            ABead.Called("y-1", "Held") with { ParentId = "y" }).ToBoard(Default);
        var collapsed = new CollapsedRows();

        collapsed.CollapseAll(board);

        Assert.Equal(["The outer epic", "The second epic"], collapsed.Draws(board.Rows).Select(row => row.Bead.Title));
    }

    [Fact]
    public void CollapsesTheRowsBelowATopRowAsWellWhenAPersonCollapsesAll()
    {
        var board = Of(
            ABead.Epic("outer", "The outer epic"),
            ABead.Epic("inner", "The inner epic") with { ParentId = "outer" },
            ABead.Called("x-1", "Held deep") with { ParentId = "inner" }).ToBoard(Default);
        var collapsed = new CollapsedRows();

        collapsed.CollapseAll(board);
        collapsed.Toggle("outer");

        Assert.Equal(["The outer epic", "The inner epic"], collapsed.Draws(board.Rows).Select(row => row.Bead.Title));
    }

    [Fact]
    public void CollapsesTheUnparentedRowWhenAPersonCollapsesAllOnABoardThatDrawsIt()
    {
        var board = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" },
            ABead.Called("x-2", "Loose")).ToBoard(Default);
        var collapsed = new CollapsedRows();

        collapsed.CollapseAll(board);

        Assert.Empty(collapsed.DrawsUnparented(board.Unparented));
    }

    [Fact]
    public void LeavesTheUnparentedRowOpenWhenAPersonCollapsesAllOnABoardThatDoesNotDrawIt()
    {
        var loose = Of(ABead.Called("x-2", "Loose")).ToBoard(Default).Unparented;
        var withNoLooseBead = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" }).ToBoard(Default);
        var collapsed = new CollapsedRows();

        collapsed.CollapseAll(withNoLooseBead);

        Assert.Equal(["Loose"], collapsed.DrawsUnparented(loose).Select(row => row.Bead.Title));
    }

    [Fact]
    public void BringsARowThatArrivesAfterACollapseAllInOpen()
    {
        var before = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" }).ToBoard(Default);
        var after = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" },
            ABead.Epic("y", "The new epic"),
            ABead.Called("y-1", "Held by the new epic") with { ParentId = "y" }).ToBoard(Default).Rows;
        var collapsed = new CollapsedRows();

        collapsed.CollapseAll(before);

        Assert.Equal(
            ["The epic", "The new epic", "Held by the new epic"],
            collapsed.Draws(after).Select(row => row.Bead.Title));
    }

    [Fact]
    public void SaysThatNothingIsLeftToCollapseOnceAPersonCollapsesAll()
    {
        var board = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" },
            ABead.Called("x-2", "Loose")).ToBoard(Default);
        var collapsed = new CollapsedRows();

        Assert.False(collapsed.LeavesNothingToCollapse(board));

        collapsed.CollapseAll(board);

        Assert.True(collapsed.LeavesNothingToCollapse(board));
    }

    [Fact]
    public void SaysThatARowIsLeftToCollapseOnceAPersonOpensOne()
    {
        var board = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" },
            ABead.Called("x-2", "Loose")).ToBoard(Default);
        var collapsed = new CollapsedRows();
        collapsed.CollapseAll(board);

        collapsed.ToggleUnparented();

        Assert.False(collapsed.LeavesNothingToCollapse(board));
    }

    [Fact]
    public void SaysThatNothingIsLeftToCollapseWhenNoRowOnTheBoardHoldsABead()
    {
        var board = Of(ABead.Epic("x", "The empty epic")).ToBoard(Default);

        Assert.True(new CollapsedRows().LeavesNothingToCollapse(board));
    }

    [Fact]
    public void SaysThatItHoldsNoRowUntilAPersonCollapsesOne()
    {
        var collapsed = new CollapsedRows();

        Assert.False(collapsed.HoldsAny);

        collapsed.Toggle("x");

        Assert.True(collapsed.HoldsAny);
    }

    [Fact]
    public void SaysThatItHoldsARowWhenOnlyTheUnparentedRowIsCollapsed()
    {
        var collapsed = new CollapsedRows();

        collapsed.ToggleUnparented();

        Assert.True(collapsed.HoldsAny);
    }

    [Fact]
    public void OpensEveryRowAndHoldsNoneOnceAPersonExpandsAll()
    {
        var everything = Of(
            ABead.Epic("x", "The epic"),
            ABead.Called("x-1", "Held") with { ParentId = "x" },
            ABead.Epic("y", "The other epic"),
            ABead.Called("y-1", "Also held") with { ParentId = "y" }).ToBoard(Default);
        var collapsed = new CollapsedRows();
        collapsed.CollapseAll(everything);

        collapsed.OpenAll();

        Assert.False(collapsed.HoldsAny);
        Assert.Equal(
            ["The epic", "Held", "The other epic", "Also held"],
            collapsed.Draws(everything.Rows).Select(row => row.Bead.Title));
    }

    [Fact]
    public void OpensACollapsedRowWhoseBeadLeftTheBacklog()
    {
        var collapsed = new CollapsedRows();
        collapsed.Toggle("x");

        collapsed.KeepOnly(["y"]);

        Assert.False(collapsed.Holds("x"));
        Assert.False(collapsed.HoldsAny);
    }

    [Fact]
    public void KeepsARowCollapsedWhileItsBeadStaysInTheBacklog()
    {
        var collapsed = new CollapsedRows();
        collapsed.Toggle("x");

        collapsed.KeepOnly(["x", "y"]);

        Assert.True(collapsed.Holds("x"));
    }
}
