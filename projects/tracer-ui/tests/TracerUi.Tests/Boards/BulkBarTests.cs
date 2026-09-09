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
