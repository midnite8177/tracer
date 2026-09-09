namespace TracerUi.Tests;

public sealed class FakeTimeProviderTests
{
    private static readonly DateTimeOffset Start = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

    [Fact]
    public void ReadsTheStartUntilATestMovesItForward()
    {
        var clock = new FakeTimeProvider(Start);

        clock.Advance(TimeSpan.FromSeconds(5));

        Assert.Equal(Start + TimeSpan.FromSeconds(5), clock.GetUtcNow());
    }

    [Fact]
    public void CompletesADelayAsSoonAsATestMovesTheClockPastItInsteadOfWaitingForRealTime()
    {
        var clock = new FakeTimeProvider(Start);
        var delay = Task.Delay(TimeSpan.FromSeconds(30), clock);

        Assert.False(delay.IsCompleted);

        clock.Advance(TimeSpan.FromSeconds(30));

        Assert.True(delay.IsCompletedSuccessfully);
    }
}
