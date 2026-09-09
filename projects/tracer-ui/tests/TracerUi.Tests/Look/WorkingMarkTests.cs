using Bunit;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Tests;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Look;

public sealed class WorkingMarkTests : BunitContext
{
    private static readonly DateTimeOffset Start = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

    private readonly FakeTimeProvider clock = new(Start);

    public WorkingMarkTests() => Services.AddSingleton<TimeProvider>(clock);

    [Fact]
    public void ShowsNoMarkTheMomentAWriteStarts()
    {
        var mark = Render<WorkingMark>(p => p.Add(m => m.Writing, true));

        Assert.Empty(mark.FindAll(".working-mark"));
    }

    [Fact]
    public void ShowsNoMarkWhenTheWriteAnswersBeforeTheWaitElapses()
    {
        var mark = Render<WorkingMark>(p => p.Add(m => m.Writing, true));

        mark.Render(p => p.Add(m => m.Writing, false));
        clock.Advance(WorkingMark.WaitBeforeShowing);

        Assert.Empty(mark.FindAll(".working-mark"));
    }

    [Fact]
    public void ShowsTheMarkOnceTheWriteOutrunsTheWait()
    {
        var mark = Render<WorkingMark>(p => p.Add(m => m.Writing, true));

        clock.Advance(WorkingMark.WaitBeforeShowing);

        mark.WaitForAssertion(() => Assert.Single(mark.FindAll(".working-mark")));
    }

    [Fact]
    public void KeepsTheMarkForItsFloorEvenWhenTheWriteAnswersJustAfterItAppears()
    {
        var mark = TheMarkThatHasAlreadyShown();

        mark.Render(p => p.Add(m => m.Writing, false));
        clock.Advance(WorkingMark.Floor - TimeSpan.FromMilliseconds(1));

        Assert.Single(mark.FindAll(".working-mark"));
    }

    [Fact]
    public void HidesTheMarkOnceItsFloorElapsesAfterTheWriteAnswered()
    {
        var mark = TheMarkThatHasAlreadyShown();
        mark.Render(p => p.Add(m => m.Writing, false));

        clock.Advance(WorkingMark.Floor);

        mark.WaitForAssertion(() => Assert.Empty(mark.FindAll(".working-mark")));
    }

    [Fact]
    public void ShowsAnImmediateMarkTheMomentAWriteStartsWithNoWaitFirst()
    {
        var mark = Render<WorkingMark>(p => p.Add(m => m.Writing, true).Add(m => m.Immediate, true));

        Assert.Single(mark.FindAll(".working-mark"));
    }

    [Fact]
    public void KeepsAnImmediateMarkForItsFloorEvenWhenTheWriteAnswersRightAway()
    {
        var mark = Render<WorkingMark>(p => p.Add(m => m.Writing, true).Add(m => m.Immediate, true));

        mark.Render(p => p.Add(m => m.Writing, false).Add(m => m.Immediate, true));
        clock.Advance(WorkingMark.Floor - TimeSpan.FromMilliseconds(1));

        Assert.Single(mark.FindAll(".working-mark"));
    }

    [Fact]
    public void HidesAnImmediateMarkOnceItsFloorElapsesAfterTheWriteAnswered()
    {
        var mark = Render<WorkingMark>(p => p.Add(m => m.Writing, true).Add(m => m.Immediate, true));
        mark.Render(p => p.Add(m => m.Writing, false).Add(m => m.Immediate, true));

        clock.Advance(WorkingMark.Floor);

        mark.WaitForAssertion(() => Assert.Empty(mark.FindAll(".working-mark")));
    }

    // A mark whose wait has already elapsed while still busy, so the tests of the floor start from
    // a mark that a reader would actually see rather than racing the render that shows it.
    private IRenderedComponent<WorkingMark> TheMarkThatHasAlreadyShown()
    {
        var mark = Render<WorkingMark>(p => p.Add(m => m.Writing, true));
        clock.Advance(WorkingMark.WaitBeforeShowing);
        mark.WaitForAssertion(() => Assert.Single(mark.FindAll(".working-mark")));
        return mark;
    }
}
