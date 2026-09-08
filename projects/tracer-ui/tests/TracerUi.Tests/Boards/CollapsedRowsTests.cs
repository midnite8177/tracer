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

        collapsed.Clear();

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

        collapsed.Clear();

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
}
