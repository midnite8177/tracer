using JidokaUi.Core.Jidoka;

namespace JidokaUi.Tests.Jidoka;

public sealed class AntigravityUsageTests : IDisposable
{
    private static readonly DateTimeOffset Now = new(2026, 1, 1, 12, 0, 0, TimeSpan.Zero);

    private readonly TempDirectory home = new();

    [Fact]
    public void ReadsEachBucketWithItsFiveHourAndWeeklyUseAndReset()
    {
        Write(TheFile(Now.AddMinutes(-3)));

        var reading = TheUsage().ReadingAt(Now);

        Assert.NotNull(reading);
        Assert.Equal(Now.AddMinutes(-3), reading.CheckedAt);
        Assert.Equal(
            [
                new UsageBucket(
                    "gemini-3-pro",
                    new UsageWindow(42, Now.AddMinutes(119)),
                    new UsageWindow(18.5, Now.AddDays(3))),
                new UsageBucket("gemini-3-flash", new UsageWindow(7, null), null),
            ],
            reading.Buckets);
    }

    [Fact]
    public void WordsAWindowByItsUseAndTheTimeToItsReset()
    {
        Assert.Equal("42% used, resets in 1h59m", new UsageWindow(42, Now.AddMinutes(119)).Words(Now));
        Assert.Equal("18.5% used, resets in 45s", new UsageWindow(18.5, Now.AddSeconds(45)).Words(Now));
        Assert.Equal("0% used, resets in 9m", new UsageWindow(0, Now.AddMinutes(9)).Words(Now));
        Assert.Equal("100% used, has reset", new UsageWindow(100, Now.AddMinutes(-1)).Words(Now));
        Assert.Equal("7% used", new UsageWindow(7, null).Words(Now));
    }

    [Fact]
    public void GivesNoReadingForAFileThatTheSchedulerRemoved()
    {
        Assert.Null(TheUsage().ReadingAt(Now));
    }

    [Fact]
    public void GivesNoReadingForOneThatT3CheckedMoreThanTenMinutesAgo()
    {
        Write(TheFile(Now.AddMinutes(-10).AddSeconds(-1)));

        Assert.Null(TheUsage().ReadingAt(Now));
    }

    [Fact]
    public void GivesAReadingForOneThatT3CheckedExactlyTenMinutesAgo()
    {
        Write(TheFile(Now.AddMinutes(-10)));

        Assert.NotNull(TheUsage().ReadingAt(Now));
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("[]")]
    [InlineData("""{"buckets": {}}""")]
    [InlineData("""{"checkedAt": "yesterday", "buckets": {}}""")]
    [InlineData("""{"checkedAt": 1767268800}""")]
    [InlineData("""{"checkedAt": 1767268800, "buckets": []}""")]
    public void GivesNoReadingForAFileOfAnotherShape(string content)
    {
        Write(content);

        Assert.Null(TheUsage().ReadingAt(new DateTimeOffset(2026, 1, 1, 12, 0, 0, TimeSpan.Zero)));
    }

    [Fact]
    public void ReadsAWindowThatNamesNoUseAsNoWindowAndNotAsAUseOfZero()
    {
        Write(
            $$$"""
            {"checkedAt": {{{Now.ToUnixTimeSeconds()}}}, "buckets": {"gemini-3-pro": {
              "session": {"id": "gemini-3-pro-5h", "resetsAt": 1767268800},
              "weekly": {"id": "gemini-3-pro-weekly", "usedPercent": "most"} } } }
            """);

        var bucket = Assert.Single(TheUsage().ReadingAt(Now)?.Buckets ?? []);

        Assert.Null(bucket.Session);
        Assert.Null(bucket.Weekly);
    }

    public void Dispose() => home.Dispose();

    private static string TheFile(DateTimeOffset checkedAt) =>
        $$$"""
        {"checkedAt": {{{checkedAt.ToUnixTimeSeconds()}}}, "buckets": {
          "gemini-3-pro": {
            "session": {"id": "gemini-3-pro-5h", "usedPercent": 42.0,
                        "resetsAt": {{{Now.AddMinutes(119).ToUnixTimeSeconds()}}}, "windowDurationMins": 300.0},
            "weekly": {"id": "gemini-3-pro-weekly", "usedPercent": 18.5,
                       "resetsAt": {{{Now.AddDays(3).ToUnixTimeSeconds()}}}, "windowDurationMins": 10080.0}},
          "gemini-3-flash": {
            "session": {"id": "gemini-3-flash-5h", "usedPercent": 7.0, "resetsAt": null, "windowDurationMins": null} } } }
        """;

    private AntigravityUsage TheUsage() => new(new JidokaHome(home.Path));

    private void Write(string content)
    {
        var folder = home.CreateSubdirectory("usage");
        File.WriteAllText(Path.Combine(folder, "antigravity.json"), content);
    }
}
