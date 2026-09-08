using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class RowPressTests
{
    [Fact]
    public void ReadsAReleaseFarFromThePressAsADrag()
    {
        var press = new RowPress();
        press.StartedAt(100, 50);

        Assert.True(press.Dragged(140, 50));
    }

    [Fact]
    public void ReadsAReleaseOnThePressAsAClick()
    {
        var press = new RowPress();
        press.StartedAt(100, 50);

        Assert.False(press.Dragged(100, 50));
    }

    [Fact]
    public void ReadsTheSmallTravelOfAHandThatHoldsAMouseAsAClick()
    {
        var press = new RowPress();
        press.StartedAt(100, 50);

        Assert.False(press.Dragged(102, 51));
    }

    [Fact]
    public void ReadsATravelDownTheScreenAsADragToo()
    {
        var press = new RowPress();
        press.StartedAt(100, 50);

        Assert.True(press.Dragged(100, 90));
    }

    [Fact]
    public void ReadsAReleaseThatFollowsNoPressAsAClick()
    {
        var press = new RowPress();

        Assert.False(press.Dragged(400, 400));
    }

    [Fact]
    public void ForgetsADragSoTheNextReleaseAsksAboutTheNextPressAlone()
    {
        var press = new RowPress();
        press.StartedAt(100, 50);
        press.Dragged(400, 400);

        Assert.False(press.Dragged(400, 400));
    }
}
