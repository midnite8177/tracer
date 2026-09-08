using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BacklogStatusTests
{
    private static Backlog Of(IReadOnlyList<Bead> beads, IReadOnlyList<string> ready) =>
        new(beads, ready, new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal));

    [Fact]
    public void ReadsABeadThatBdCallsReadyAsReady()
    {
        var bead = ABead.Called("x-1", "First");

        Assert.Equal("ready", Of([bead], ["x-1"]).StatusOf(bead).Text);
    }

    [Fact]
    public void ReadsAnInProgressBeadAsInProgressWithItsAssignee()
    {
        var bead = ABead.Called("x-1", "First") with { Status = "in_progress", Assignee = "claude" };

        Assert.Equal("in progress (claude)", Of([bead], []).StatusOf(bead).Text);
    }

    [Fact]
    public void ReadsADeferredBeadAsDeferred()
    {
        var bead = ABead.Called("x-1", "First") with { Status = "deferred" };

        Assert.Equal("deferred", Of([bead], []).StatusOf(bead).Text);
    }

    [Fact]
    public void ReadsABeadWithTheHumanLabelAsOneThatNeedsYouEvenWhenBdCallsItReady()
    {
        var bead = ABead.Called("x-1", "First") with { Labels = ["human"] };

        Assert.Equal("needs you", Of([bead], ["x-1"]).StatusOf(bead).Text);
    }

    [Fact]
    public void FallsBackToTheStatusThatBdPrintsForABeadThatIsNeitherReadyNorBlocked()
    {
        var bead = ABead.Called("x-1", "First") with { Status = "closed" };

        Assert.Equal("closed", Of([bead], []).StatusOf(bead).Text);
    }

    [Fact]
    public void NamesTheTitleOfEachBeadThatBlocksABlockedBead()
    {
        var blocked = ABead.Called("x-1", "First");
        var blocker = ABead.Called("x-2", "The adapter");
        var backlog = new Backlog(
            [blocked, blocker],
            [],
            new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
            {
                ["x-1"] = ["x-2"],
            });

        Assert.Equal("blocked by The adapter", backlog.StatusOf(blocked).Text);
    }

    [Fact]
    public void CountsTheBlockersAfterTheFirstTwoInsteadOfNamingThemAll()
    {
        var blocked = ABead.Called("x-1", "First");
        var backlog = new Backlog(
            [blocked, ABead.Called("x-2", "Two"), ABead.Called("x-3", "Three"), ABead.Called("x-4", "Four")],
            [],
            new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
            {
                ["x-1"] = ["x-2", "x-3", "x-4"],
            });

        Assert.Equal("blocked by Two, Three +1", backlog.StatusOf(blocked).Text);
    }

    [Fact]
    public void NamesABlockerByItsIdWhenNoBeadOfTheBacklogCarriesThatId()
    {
        var blocked = ABead.Called("x-1", "First");
        var backlog = new Backlog(
            [blocked],
            [],
            new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
            {
                ["x-1"] = ["x-99"],
            });

        Assert.Equal("blocked by x-99", backlog.StatusOf(blocked).Text);
    }

    [Fact]
    public void ReadsAClosedBeadAsClosedEvenWhenItCarriesTheHumanLabel()
    {
        var bead = ABead.Called("x-1", "First") with { Status = "closed", Labels = ["human"] };

        Assert.Equal("closed", Of([bead], []).StatusOf(bead).Text);
    }
}
