using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BacklogDependencyTests
{
    private static Backlog Of(IReadOnlyList<Bead> beads) =>
        new(beads, [], new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal));

    // The bead that one link names, as one line, so a failure reads as a sentence.
    private static string Named(BeadLink link) => $"{link.Id} {link.Title}";

    [Fact]
    public void NamesTheBeadsThatBlockOneBeadWithTheirTitles()
    {
        var groundwork = ABead.Called("x-9", "Groundwork");
        var bead = ABead.Called("x-1", "First") with { Blockers = ["x-9"] };

        Assert.Equal(
            ["x-9 Groundwork"],
            Of([bead, groundwork]).BlockersOf(bead).Select(Named));
    }

    [Fact]
    public void NamesTheBeadsThatOneBeadBlocksWithTheirTitles()
    {
        var bead = ABead.Called("x-1", "First");
        var waiting = ABead.Called("x-2", "The next slice") with { Blockers = ["x-1"] };

        Assert.Equal(
            ["x-2 The next slice"],
            Of([bead, waiting]).DependentsOf(bead).Select(Named));
    }

    [Fact]
    public void KeepsNamingABeadThatOneBeadBlocksAfterThatBeadStopsBeingBlocked()
    {
        var bead = ABead.Called("x-1", "First") with { Status = "closed" };
        var freed = ABead.Called("x-2", "The next slice") with { Blockers = ["x-1"] };

        Assert.Equal(
            ["x-2 The next slice"],
            Of([bead, freed]).DependentsOf(bead).Select(Named));
    }

    [Fact]
    public void FallsBackToTheIdOfABeadThatThisBacklogDoesNotHold()
    {
        var bead = ABead.Called("x-1", "First") with { Blockers = ["x-9"] };

        Assert.Equal(["x-9 x-9"], Of([bead]).BlockersOf(bead).Select(Named));
    }

    [Fact]
    public void SaysThatItAnswersForNoStatusAndNoTypeOfABeadThatThisBacklogDoesNotHold()
    {
        var bead = ABead.Called("x-1", "First") with { Blockers = ["x-9"] };

        var blocker = Assert.Single(Of([bead]).BlockersOf(bead));
        Assert.Equal(string.Empty, blocker.Type);
        Assert.Equal("unknown", blocker.Status.Appearance);
        Assert.Equal("not in this project", blocker.Status.Text);
    }

    [Fact]
    public void NamesTheEpicThatHoldsOneBeadWithItsTitle()
    {
        var epic = ABead.Epic("x", "The epic");
        var bead = ABead.Called("x-1", "First") with { ParentId = "x" };

        Assert.Equal("x The epic", Named(Assert.IsType<BeadLink>(Of([bead, epic]).EpicOf(bead))));
    }

    [Fact]
    public void NamesNoEpicForABeadThatNoEpicHolds()
    {
        var bead = ABead.Called("x-1", "First");

        Assert.Null(Of([bead]).EpicOf(bead));
    }
}
