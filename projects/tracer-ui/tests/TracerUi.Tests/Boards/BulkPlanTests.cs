using TracerUi.Core.Beads;
using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BulkPlanTests
{
    [Fact]
    public void SaysHowManyBeadsTakeTheLabelBeforeTheActionCommits()
    {
        var plan = BulkPlan.For(BulkAction.AddTheLabel("human"), [ABead.Called("x-1", "One"), ABead.Called("x-2", "Two")]);

        Assert.Equal("Add the label human to 2 beads.", plan.Summary);
    }

    [Fact]
    public void CountsOneBeadInTheSingular()
    {
        var plan = BulkPlan.For(BulkAction.DeferThem(), [ABead.Called("x-1", "One")]);

        Assert.Equal("Defer 1 bead.", plan.Summary);
    }

    [Fact]
    public void NamesEveryBeadOfTheActionInTheOrderTheBoardGaveThem()
    {
        var plan = BulkPlan.For(BulkAction.SetTheType("bug"), [ABead.Called("x-2", "Two"), ABead.Called("x-1", "One")]);

        Assert.Equal(["x-2", "x-1"], plan.Steps.Select(step => step.BeadId));
        Assert.Equal(["Two", "One"], plan.Steps.Select(step => step.Title));
    }

    [Fact]
    public void GivesEveryBeadOfACloseTheSharedReasonThatThePersonTyped()
    {
        var plan = BulkPlan.For(BulkAction.CloseThem("The board shows it now"), TwoBeads);

        Assert.Equal(
            ["The board shows it now", "The board shows it now"],
            plan.Steps.Select(step => step.Reason));
        Assert.Equal("Close 2 beads. They all take the same reason.", plan.Summary);
    }

    [Fact]
    public void KeepsTheReasonThatThePersonWroteForOneBeadOfACloseAndLeavesTheRestAlone()
    {
        var plan = BulkPlan.For(BulkAction.CloseThem("Stale"), TwoBeads);

        var edited = plan.WithReasonFor("x-2", "This one shipped");

        Assert.Equal(["Stale", "This one shipped"], edited.Steps.Select(step => step.Reason));
        Assert.Equal("Close 2 beads. 1 of them takes a reason of its own.", edited.Summary);
    }

    [Fact]
    public void CountsTheBeadsOfACloseThatTookAReasonOfTheirOwnInThePlural()
    {
        var plan = BulkPlan.For(BulkAction.CloseThem("Stale"), TwoBeads)
            .WithReasonFor("x-1", "This one shipped")
            .WithReasonFor("x-2", "This one was a duplicate");

        Assert.Equal("Close 2 beads. 2 of them take a reason of their own.", plan.Summary);
    }

    [Fact]
    public void RefusesToCommitACloseWhileOneBeadHasNoReason()
    {
        var plan = BulkPlan.For(BulkAction.CloseThem("Stale"), TwoBeads).WithReasonFor("x-2", "  ");

        Assert.False(plan.IsReady);
        Assert.Equal("Bead x-2 has no close reason.", plan.Problem);
    }

    [Fact]
    public void RefusesToCommitALabelActionThatNamesNoLabel()
    {
        var plan = BulkPlan.For(BulkAction.AddTheLabel("   "), TwoBeads);

        Assert.False(plan.IsReady);
    }

    [Fact]
    public void RefusesToCommitAnActionThatHoldsNoBead()
    {
        var plan = BulkPlan.For(BulkAction.DeferThem(), []);

        Assert.False(plan.IsReady);
        Assert.Equal("Select a bead first.", plan.Problem);
    }

    [Fact]
    public void CommitsADeferWhichNeedsNoValueOfItsOwn()
    {
        var plan = BulkPlan.For(BulkAction.DeferThem(), TwoBeads);

        Assert.True(plan.IsReady);
    }

    [Fact]
    public void KnowsWhatEveryVerbOfTheActionBarIsCalledAndWhichWriteItNeeds()
    {
        foreach (var verb in Enum.GetValues<BulkVerb>())
        {
            var shape = BulkVerbs.Of(verb);

            Assert.NotEqual(string.Empty, shape.Name);
            Assert.NotEqual(string.Empty, shape.Write.Command);
        }
    }

    [Fact]
    public void OffersSixVerbCategoriesAndReachesEveryVerbThroughThem()
    {
        Assert.Equal(6, BulkCategory.All.Count);
        Assert.Equal(
            [.. Enum.GetValues<BulkVerb>().Order()],
            BulkCategory.All.SelectMany(category => category.Verbs).Order());
    }

    private static IReadOnlyList<Bead> TwoBeads =>
        [ABead.Called("x-1", "One"), ABead.Called("x-2", "Two")];
}
