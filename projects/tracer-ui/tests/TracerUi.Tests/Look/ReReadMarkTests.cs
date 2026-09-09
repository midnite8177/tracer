using Bunit;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Tests;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Look;

public sealed class ReReadMarkTests : BunitContext
{
    private static readonly DateTimeOffset Start = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

    private readonly FakeTimeProvider clock = new(Start);

    public ReReadMarkTests() => Services.AddSingleton<TimeProvider>(clock);

    [Fact]
    public void KeepsWhatStandsOnTheScreenTheMomentARereadStarts()
    {
        var mark = TheMarkAround("Pick a hosting plan", rereading: true);

        Assert.Contains("Pick a hosting plan", mark.Markup, StringComparison.Ordinal);
        Assert.Empty(mark.FindAll(".re-read-mark"));
        Assert.Empty(mark.FindAll(".re-read-dim"));
    }

    [Fact]
    public void ShowsNoMarkWhenTheRereadAnswersBeforeTheWaitElapses()
    {
        var mark = TheMarkAround("Pick a hosting plan", rereading: true);

        mark.Render(p => p.Add(m => m.Rereading, false));
        clock.Advance(WorkingMark.WaitBeforeShowing);

        Assert.Empty(mark.FindAll(".re-read-mark"));
    }

    [Fact]
    public void DimsWhatStandsOnTheScreenAndShowsTheMarkOnceTheRereadOutrunsTheWait()
    {
        var mark = TheMarkAround("Pick a hosting plan", rereading: true);

        clock.Advance(WorkingMark.WaitBeforeShowing);

        mark.WaitForAssertion(() => Assert.Single(mark.FindAll(".re-read-mark")));
        Assert.Contains("Pick a hosting plan", mark.Find(".re-read-dim").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void KeepsTheDimAndTheMarkForTheFloorEvenWhenTheRereadAnswersJustAfterItAppears()
    {
        var mark = TheMarkThatHasAlreadyShown();

        mark.Render(p => p.Add(m => m.Rereading, false));
        clock.Advance(WorkingMark.Floor - TimeSpan.FromMilliseconds(1));

        Assert.Single(mark.FindAll(".re-read-mark"));
        Assert.Single(mark.FindAll(".re-read-dim"));
    }

    [Fact]
    public void HidesTheDimAndTheMarkOnceTheFloorElapsesAfterTheRereadAnswered()
    {
        var mark = TheMarkThatHasAlreadyShown();
        mark.Render(p => p.Add(m => m.Rereading, false));

        clock.Advance(WorkingMark.Floor);

        mark.WaitForAssertion(() =>
        {
            Assert.Empty(mark.FindAll(".re-read-mark"));
            Assert.Empty(mark.FindAll(".re-read-dim"));
        });
    }

    private IRenderedComponent<ReReadMark> TheMarkAround(string content, bool rereading) =>
        Render<ReReadMark>(p => p.Add(m => m.Rereading, rereading).AddChildContent($"<p>{content}</p>"));

    private IRenderedComponent<ReReadMark> TheMarkThatHasAlreadyShown()
    {
        var mark = TheMarkAround("Pick a hosting plan", rereading: true);
        clock.Advance(WorkingMark.WaitBeforeShowing);
        mark.WaitForAssertion(() => Assert.Single(mark.FindAll(".re-read-mark")));
        return mark;
    }
}
