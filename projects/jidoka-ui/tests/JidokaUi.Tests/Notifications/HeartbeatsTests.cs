using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Notifications;

namespace JidokaUi.Tests.Notifications;

public sealed class HeartbeatsTests : IDisposable
{
    private static readonly DateTimeOffset Now = new(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);

    private readonly TempDirectory home = new();

    [Fact]
    public void ReadsTheAgeOfAHeartbeatFromTheSecondOfItsLastBeat()
    {
        Write("a", Beat(Now.AddSeconds(-42), 90));

        Assert.Equal(TimeSpan.FromSeconds(42), TheHeartbeats().BeatOf("a", Now)?.Age);
    }

    [Theory]
    [InlineData(25, 25, false)]
    [InlineData(25, 26, true)]
    [InlineData(300, 200, false)]
    public void CallsAHeartbeatStaleOnlyWhenItIsOlderThanTheLimitInItsOwnFile(int limit, int age, bool stale)
    {
        Write("a", Beat(Now.AddSeconds(-age), limit));

        Assert.Equal(stale, TheHeartbeats().BeatOf("a", Now)?.IsStale);
    }

    [Fact]
    public void CallsAHeartbeatThatRecordsAStopStaleHoweverYoungItIs()
    {
        Write("a", WithStopped(Now.AddSeconds(-42), "true"));

        var beat = TheHeartbeats().BeatOf("a", Now);

        Assert.Equal(true, beat?.IsStale);
        Assert.Equal(TimeSpan.FromSeconds(42), beat?.Age);
    }

    [Theory]
    [InlineData("false")]
    [InlineData("null")]
    [InlineData("\"yes\"")]
    [InlineData("1")]
    public void ReadsAStoppedFieldThatIsNotTrueAsNoStop(string stopped)
    {
        Write("a", WithStopped(Now.AddSeconds(-42), stopped));

        Assert.Equal(false, TheHeartbeats().BeatOf("a", Now)?.IsStale);
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("[]")]
    [InlineData("""{"epic": "a"}""")]
    [InlineData("""{"time": "yesterday", "fresh_seconds": 90}""")]
    [InlineData("""{"time": 1767268800}""")]
    [InlineData("""{"time": 1767268800, "fresh_seconds": "ninety"}""")]
    [InlineData("""{"time": 1767268800, "fresh_seconds": 0}""")]
    public void GivesNoBeatForAFileThatHoldsNoTimeAndNoFreshLimit(string content)
    {
        Write("a", content);

        Assert.Null(TheHeartbeats().BeatOf("a", Now));
    }

    [Fact]
    public void GivesNoBeatForAnEpicWithoutAHeartbeatFile()
    {
        Assert.Null(TheHeartbeats().BeatOf("a", Now));
    }

    [Fact]
    public void GivesNoBeatForAnIdThatNamesNoFile()
    {
        Assert.Null(TheHeartbeats().BeatOf("../a", Now));
    }

    public void Dispose() => home.Dispose();

    private static string Beat(DateTimeOffset time, int freshSeconds) =>
        $$"""{"epic": "a", "time": {{time.ToUnixTimeSeconds()}}, "session": "s1", "fresh_seconds": {{freshSeconds}}}""";

    private static string WithStopped(DateTimeOffset time, string stopped) =>
        $$"""{"epic": "a", "time": {{time.ToUnixTimeSeconds()}}, "session": null, "fresh_seconds": 90, "stopped": {{stopped}}}""";

    private Heartbeats TheHeartbeats() => new(new JidokaHome(home.Path));

    private void Write(string epic, string content)
    {
        var folder = home.CreateSubdirectory("heartbeat");
        File.WriteAllText(Path.Combine(folder, $"{epic}.json"), content);
    }
}
