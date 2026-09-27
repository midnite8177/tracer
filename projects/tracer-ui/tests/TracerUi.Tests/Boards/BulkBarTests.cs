using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Boards;
using TracerUi.Tests.Beads;
using TracerUi.Web.Components.Pages;

namespace TracerUi.Tests.Boards;

/// <summary>The bulk bar as a browser draws it, row by row, over the run of a bulk action.</summary>
public sealed class BulkBarTests : BunitContext
{
    private readonly TwoProjects projects = new();

    public BulkBarTests()
    {
        projects.Bd.DeclaresEveryWrite();
        projects.RegisterOn(Services);
        Services.AddSingleton(new BulkWriter(projects.Adapter));
    }

    [Fact]
    public void ShowsEveryRowAsWaitingOnceThePlanStandsAndBeforeAnyWriteRuns()
    {
        var bar = TheBarWithTwoBeadsDeferred(onRetry: null);

        bar.Find("#bulk-review").Click();

        Assert.Equal(["waiting", "waiting"], RowWords(bar));
    }

    [Fact]
    public void MarksTheRowThatIsWritingAtOnceWithNoWaitAndLeavesTheRestWaiting()
    {
        projects.Bd.Holds("defer x-1");
        var bar = TheBarWithTwoBeadsDeferred(onRetry: null);
        bar.Find("#bulk-review").Click();

        bar.Find("#bulk-commit").Click();

        Assert.Equal(["writing", "waiting"], RowWords(bar));
        Assert.Single(bar.FindAll(".working-mark"));
    }

    [Fact]
    public void TurnsARowWrittenOnceItsWriteAnswersAndStartsTheNextOne()
    {
        projects.Bd.Holds("defer x-1").Holds("defer x-2");
        var bar = TheBarWithTwoBeadsDeferred(onRetry: null);
        bar.Find("#bulk-review").Click();
        bar.Find("#bulk-commit").Click();

        projects.Bd.Answers("defer x-1", string.Empty);

        bar.WaitForAssertion(() => Assert.Equal(["written", "writing"], RowWords(bar)));
    }

    [Fact]
    public void FailsARowInPlaceWithTheMessageThatBdGaveAndStillWritesTheRestOfTheSelection()
    {
        var bar = TheBarWithTwoBeadsDeferred(onRetry: null);
        projects.Bd.Fails("defer x-1", "issue x-1 not found");
        bar.Find("#bulk-review").Click();

        bar.Find("#bulk-commit").Click();

        Assert.Equal(["failed", "written"], RowWords(bar));
        Assert.Contains("issue x-1 not found", bar.Find(".board-bulk-row-failed .board-bulk-row-message").TextContent);
    }

    [Fact]
    public void KeepsThePlanTableOnScreenAfterTheRunEndsWithASummaryAndAClose()
    {
        var bar = TheBarWithTwoBeadsDeferred(onRetry: null);
        bar.Find("#bulk-review").Click();

        bar.Find("#bulk-commit").Click();

        Assert.Equal(["written", "written"], RowWords(bar));
        Assert.Contains("bd wrote 2 beads.", bar.Find(".board-bulk-plan .board-bulk-message").TextContent);
        Assert.Empty(bar.FindAll("#bulk-commit"));

        bar.Find("#bulk-close").Click();

        Assert.Empty(bar.FindAll(".board-bulk-plan"));
    }

    [Fact]
    public void SelectsTheFailedBeadsWhenThePersonAsksToRetryWithoutClosingTheTable()
    {
        IReadOnlyList<string>? retried = null;
        var bar = TheBarWithTwoBeadsDeferred(onRetry: ids => retried = ids);
        projects.Bd.Fails("defer x-1", "issue x-1 not found");
        bar.Find("#bulk-review").Click();
        bar.Find("#bulk-commit").Click();

        bar.Find("#bulk-retry").Click();

        Assert.Equal(["x-1"], retried);
        Assert.Single(bar.FindAll(".board-bulk-plan"));
    }

    [Fact]
    public void LeavesAClosedEpicOutOfTheMoveIntoAnEpicAndKeepsADeferredOne()
    {
        var bar = Render<BulkBar>(parameters =>
        {
            parameters.Add(component => component.Project, projects.First);
            parameters.Add(component => component.Selected, [ABead.Called("x-1", "One")]);
            parameters.Add(component => component.Epics,
            [
                ABead.Epic("e-1", "The open epic"),
                ABead.Epic("e-2", "The finished epic") with { Status = StoredStatus.Closed },
                ABead.Epic("e-3", "The parked epic") with { Status = StoredStatus.Deferred },
            ]);
        });

        bar.Find("#bulk-category").Change(BulkCategory.Epic.Name);

        Assert.Equal(
            ["Pick an epic", "The open epic", "The parked epic"],
            bar.FindAll("#bulk-epic option").Select(offered => offered.TextContent));
    }

    [Fact]
    public void DropsThePickedEpicOfTheMoveOnceARereadShowsItClosedAndMovesOnlyIntoTheNextPick()
    {
        projects.Bd
            .Prints("update x-1 --parent e-1", string.Empty)
            .Prints("update x-1 --parent e-2", string.Empty);
        var bar = TheBarThatMovesOneBead([ABead.Epic("e-1", "The first epic"), ABead.Epic("e-2", "The second epic")]);
        bar.Find("#bulk-epic").Change("e-1");

        TheEpicsReadAgain(bar, [TheFirstEpicClosed, ABead.Epic("e-2", "The second epic")]);

        Assert.Equal(string.Empty, AnEpicPicker.ThePickedEpic(bar, "bulk-epic"));
        bar.Find("#bulk-review").Click();
        Assert.True(bar.Find("#bulk-commit").HasAttribute("disabled"));

        bar.Find("#bulk-epic").Change("e-2");
        bar.Find("#bulk-review").Click();
        bar.Find("#bulk-commit").Click();

        Assert.Contains("update x-1 --parent e-2", projects.Bd.Invocations);
        Assert.DoesNotContain("update x-1 --parent e-1", projects.Bd.Invocations);
    }

    [Fact]
    public void DropsThePickedEpicOfTheMoveOnceARereadNoLongerHoldsIt()
    {
        var bar = TheBarThatMovesOneBead([ABead.Epic("e-1", "The first epic"), ABead.Epic("e-2", "The second epic")]);
        bar.Find("#bulk-epic").Change("e-1");

        TheEpicsReadAgain(bar, [ABead.Epic("e-2", "The second epic")]);

        Assert.Equal(string.Empty, AnEpicPicker.ThePickedEpic(bar, "bulk-epic"));
    }

    [Fact]
    public void KeepsAStandingMoveIntoAnEpicThatARereadShowsClosedAndRefusesToCommitIt()
    {
        projects.Bd.Prints("update x-1 --parent e-1", string.Empty);
        var bar = TheBarThatMovesOneBead([ABead.Epic("e-1", "The first epic"), ABead.Epic("e-2", "The second epic")]);
        bar.Find("#bulk-epic").Change("e-1");
        bar.Find("#bulk-review").Click();

        TheEpicsReadAgain(bar, [TheFirstEpicClosed, ABead.Epic("e-2", "The second epic")]);

        Assert.Single(bar.FindAll(".board-bulk-plan"));
        Assert.Equal(
            "Epic e-1 no longer takes a bead. Pick another epic.",
            bar.Find(".board-bulk-plan .text-danger.board-bulk-message").TextContent.Trim());
        Assert.True(bar.Find("#bulk-commit").HasAttribute("disabled"));

        bar.Find("#bulk-commit").Click();

        Assert.DoesNotContain("update x-1 --parent e-1", projects.Bd.Invocations);
    }

    private static Bead TheFirstEpicClosed =>
        ABead.Epic("e-1", "The first epic") with { Status = StoredStatus.Closed };

    private IRenderedComponent<BulkBar> TheBarThatMovesOneBead(IReadOnlyList<Bead> epics)
    {
        var bar = Render<BulkBar>(parameters =>
        {
            parameters.Add(component => component.Project, projects.First);
            parameters.Add(component => component.Selected, [ABead.Called("x-1", "One")]);
            parameters.Add(component => component.Epics, epics);
        });
        bar.Find("#bulk-category").Change(BulkCategory.Epic.Name);
        return bar;
    }

    private static void TheEpicsReadAgain(IRenderedComponent<BulkBar> bar, IReadOnlyList<Bead> epics) =>
        bar.Render(parameters => parameters.Add(component => component.Epics, epics));

    private static IEnumerable<string> RowWords(IRenderedComponent<BulkBar> bar) =>
        bar.FindAll(".board-bulk-row-word").Select(word => word.TextContent.Trim());

    private IRenderedComponent<BulkBar> TheBarWithTwoBeadsDeferred(Action<IReadOnlyList<string>>? onRetry)
    {
        projects.Bd
            .Prints("defer x-1", string.Empty)
            .Prints("defer x-2", string.Empty);

        var bar = Render<BulkBar>(parameters =>
        {
            parameters.Add(component => component.Project, projects.First);
            parameters.Add(component => component.Selected, [ABead.Called("x-1", "One"), ABead.Called("x-2", "Two")]);
            if (onRetry is not null)
            {
                parameters.Add(component => component.OnRetry, EventCallback.Factory.Create<IReadOnlyList<string>>(this, onRetry));
            }
        });
        bar.Find("#bulk-category").Change("Defer");
        return bar;
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
