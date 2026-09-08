using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BoardFilterTests
{
    // No epic holds the bead under test, unless the test says which epics do.
    private static readonly string[] Unparented = [];

    [Fact]
    public void MatchesEveryBeadWhenNoPartOfItIsSet()
    {
        Assert.True(BoardFilter.Everything.Matches(ABead.Called("x-1", "First"), Unparented));
    }

    [Fact]
    public void KeepsOnlyTheBeadsOfTheTypeItNames()
    {
        var filter = BoardFilter.Everything with { Type = "bug" };

        Assert.True(filter.Matches(ABead.Called("x-1", "A bug") with { Type = "bug" }, Unparented));
        Assert.False(filter.Matches(ABead.Called("x-2", "A task") with { Type = "task" }, Unparented));
    }

    [Fact]
    public void IgnoresTheCaseOfATypeAsItDoesTheCaseOfALabel()
    {
        var filter = BoardFilter.Everything with { Type = "Bug" };

        Assert.True(filter.Matches(ABead.Called("x-1", "A bug") with { Type = "bug" }, Unparented));
    }

    [Fact]
    public void KeepsOnlyTheBeadsOfThePriorityItNames()
    {
        var filter = BoardFilter.Everything with { Priority = "2" };

        Assert.True(filter.Matches(ABead.Called("x-1", "Urgent") with { Priority = 2 }, Unparented));
        Assert.False(filter.Matches(ABead.Called("x-2", "Later") with { Priority = 3 }, Unparented));
    }

    [Fact]
    public void KeepsOnlyTheBeadsThatCarryTheLabelItNames()
    {
        var filter = BoardFilter.Everything with { Label = "human" };

        Assert.True(filter.Matches(ABead.Called("x-1", "Waits") with { Labels = ["human", "ui"] }, Unparented));
        Assert.False(filter.Matches(ABead.Called("x-2", "Runs") with { Labels = ["ui"] }, Unparented));
    }

    [Fact]
    public void KeepsOnlyTheBeadsThatTheEpicItNamesHolds()
    {
        var filter = BoardFilter.Everything with { Epic = "x" };

        Assert.True(filter.Matches(ABead.Called("x-1", "Held"), ["x"]));
        Assert.False(filter.Matches(ABead.Called("y-1", "Elsewhere"), ["y"]));
    }

    [Fact]
    public void KeepsABeadThatTheEpicItNamesHoldsThroughAnotherEpic()
    {
        var filter = BoardFilter.Everything with { Epic = "outer" };

        Assert.True(filter.Matches(ABead.Called("x-1", "Held deep"), ["inner", "outer"]));
    }

    [Fact]
    public void KeepsABeadWhoseTitleDescriptionOrLabelsHoldTheText()
    {
        var filter = BoardFilter.Everything with { Text = "watcher" };

        Assert.True(filter.Matches(ABead.Called("x-1", "The filesystem watcher"), Unparented));
        Assert.True(filter.Matches(
            ABead.Called("x-2", "Second").Describing("A watcher reads the directory."),
            Unparented));
        Assert.True(filter.Matches(ABead.Called("x-3", "Third") with { Labels = ["watcher"] }, Unparented));
        Assert.False(filter.Matches(
            ABead.Called("x-4", "Fourth").Describing("Nothing of the kind."),
            Unparented));
    }

    [Fact]
    public void IgnoresTheCaseAndTheSurroundingSpaceOfTheText()
    {
        var filter = BoardFilter.Everything with { Text = "  WATCHER " };

        Assert.True(filter.Matches(ABead.Called("x-1", "The filesystem watcher"), Unparented));
    }

    [Fact]
    public void KeepsOnlyTheBeadsWithNoDemoLineWhenItAsksForThem()
    {
        var filter = BoardFilter.NoDemoLine;

        Assert.True(filter.Matches(ABead.Called("x-1", "Inventory"), Unparented));
        Assert.False(filter.Matches(
            ABead.Called("x-2", "Ready").Demoing("Open the board."),
            Unparented));
    }

    [Fact]
    public void SelectsTheBeadsThatCarryTheHumanLabelWhenItAsksForTheOnesThatNeedYou()
    {
        var filter = BoardFilter.NeedsYou;

        Assert.True(filter.Matches(ABead.Called("x-1", "Waits") with { Labels = ["human"] }, Unparented));
        Assert.False(filter.Matches(ABead.Called("x-2", "Runs") with { Labels = ["ui"] }, Unparented));
    }

    [Fact]
    public void KeepsALabelOfItsOwnWhileItAlsoAsksForTheBeadsThatNeedYou()
    {
        var filter = BoardFilter.NeedsYou with { Label = "ui" };

        Assert.True(filter.Matches(ABead.Called("x-1", "Both") with { Labels = ["human", "ui"] }, Unparented));
        Assert.False(filter.Matches(ABead.Called("x-2", "Human only") with { Labels = ["human"] }, Unparented));
        Assert.False(filter.Matches(ABead.Called("x-3", "Ui only") with { Labels = ["ui"] }, Unparented));
    }

    [Fact]
    public void KeepsOnlyTheBeadThatPassesEveryPartWhenSeveralPartsNarrowTogether()
    {
        var filter = BoardFilter.Everything with { Type = "bug", Label = "ui", Epic = "x", Text = "crash" };

        Assert.True(filter.Matches(
            ABead.Called("x-1", "The board crash") with { Type = "bug", Labels = ["ui"] },
            ["x"]));
        Assert.False(filter.Matches(
            ABead.Called("x-2", "The board crash") with { Type = "task", Labels = ["ui"] },
            ["x"]));
        Assert.False(filter.Matches(
            ABead.Called("x-3", "The board crash") with { Type = "bug", Labels = ["docs"] },
            ["x"]));
        Assert.False(filter.Matches(
            ABead.Called("x-4", "The board crash") with { Type = "bug", Labels = ["ui"] },
            ["y"]));
        Assert.False(filter.Matches(
            ABead.Called("x-5", "The board reads well") with { Type = "bug", Labels = ["ui"] },
            ["x"]));
    }

    [Fact]
    public void ShowsTheOpenAndTheInProgressBeadsAndHidesTheDeferredAndTheClosedOnes()
    {
        var filter = BoardFilter.Everything;

        Assert.True(filter.Shows(StoredStatus.Open));
        Assert.True(filter.Shows(StoredStatus.InProgress));
        Assert.False(filter.Shows(StoredStatus.Deferred));
        Assert.False(filter.Shows(StoredStatus.Closed));
    }

    [Fact]
    public void ShowsTheDeferredAndTheClosedBeadsWhenItIsAskedTo()
    {
        var filter = BoardFilter.Everything with { ShowDeferred = true, ShowClosed = true };

        Assert.True(filter.Shows(StoredStatus.Deferred));
        Assert.True(filter.Shows(StoredStatus.Closed));
    }

    [Fact]
    public void ShowsTheStatusItNamesEvenWhenNothingElseAsksForThatStatus()
    {
        var filter = BoardFilter.Everything with { Status = StoredStatus.Closed };

        Assert.True(filter.Shows(StoredStatus.Closed));
        Assert.False(filter.Shows(StoredStatus.Open));
    }

    [Fact]
    public void TakesTheTypeOfARowWhenAPressNamesATypeThatItDoesNotHold()
    {
        var filter = BoardFilter.Everything.AfterAPressOnType("bug");

        Assert.Equal("bug", filter.Type);
    }

    [Fact]
    public void ClearsTheTypeWhenAPressNamesTheTypeThatItAlreadyHolds()
    {
        var filter = BoardFilter.Everything.AfterAPressOnType("bug").AfterAPressOnType("bug");

        Assert.Equal(string.Empty, filter.Type);
    }

    [Fact]
    public void KeepsEveryOtherPartWhenAPressNamesATypeForIt()
    {
        var narrowed = BoardFilter.Everything with { Label = "human", Text = "board", ShowClosed = true };

        var filter = narrowed.AfterAPressOnType("bug");

        Assert.Equal("human", filter.Label);
        Assert.Equal("board", filter.Text);
        Assert.True(filter.ShowClosed);
    }

    [Fact]
    public void TakesThePriorityOfARowWhenAPressNamesAPriorityThatItDoesNotHold()
    {
        var filter = BoardFilter.Everything.AfterAPressOnPriority("2");

        Assert.Equal("2", filter.Priority);
    }

    [Fact]
    public void ClearsThePriorityWhenAPressNamesThePriorityThatItAlreadyHolds()
    {
        var filter = BoardFilter.Everything.AfterAPressOnPriority("2").AfterAPressOnPriority("2");

        Assert.Equal(string.Empty, filter.Priority);
    }

    [Fact]
    public void KeepsEveryOtherPartWhenAPressNamesAPriorityForIt()
    {
        var narrowed = BoardFilter.Everything with { Type = "bug", Label = "ui", Text = "board" };

        var filter = narrowed.AfterAPressOnPriority("2");

        Assert.Equal(narrowed with { Priority = "2" }, filter);
    }

    [Fact]
    public void TakesALabelOfARowWhenAPressNamesALabelThatItDoesNotHold()
    {
        var filter = BoardFilter.Everything.AfterAPressOnLabel("human");

        Assert.Equal("human", filter.Label);
    }

    [Fact]
    public void ClearsTheLabelWhenAPressNamesTheLabelThatItAlreadyHolds()
    {
        var filter = BoardFilter.Everything.AfterAPressOnLabel("human").AfterAPressOnLabel("human");

        Assert.Equal(string.Empty, filter.Label);
    }

    [Fact]
    public void KeepsOnlyTheBeadsWithNoDemoLineWhenAPressNamesTheMarkerOfARowThatHasNone()
    {
        var filter = BoardFilter.Everything.AfterAPressOnTheNoDemoLineMarker();

        Assert.True(filter.RequiresNoDemoLine);
    }

    [Fact]
    public void ShowsTheBeadsWithADemoLineAgainWhenASecondPressNamesTheMarker()
    {
        var filter = BoardFilter.Everything.AfterAPressOnTheNoDemoLineMarker().AfterAPressOnTheNoDemoLineMarker();

        Assert.False(filter.RequiresNoDemoLine);
    }

    [Fact]
    public void ClearsTheTypeWhateverTheCaseOfTheWordThatThePressNames()
    {
        var filter = (BoardFilter.Everything with { Type = "Bug" }).AfterAPressOnType("bug");

        Assert.Equal(string.Empty, filter.Type);
    }
}
