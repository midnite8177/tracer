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
        Write("a", $$"""{"epic": "a", "time": {{Now.AddSeconds(-42).ToUnixTimeSeconds()}}, "session": "s1"}""");

        Assert.Equal(TimeSpan.FromSeconds(42), TheHeartbeats().AgeOf("a", Now));
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("[]")]
    [InlineData("""{"epic": "a"}""")]
    [InlineData("""{"time": "yesterday"}""")]
    public void GivesNoAgeForAFileThatHoldsNoBeat(string content)
    {
        Write("a", content);

        Assert.Null(TheHeartbeats().AgeOf("a", Now));
    }

    [Fact]
    public void GivesNoAgeForAnEpicWithoutAHeartbeatFile()
    {
        Assert.Null(TheHeartbeats().AgeOf("a", Now));
    }

    [Fact]
    public void GivesNoAgeForAnIdThatNamesNoFile()
    {
        Assert.Null(TheHeartbeats().AgeOf("../a", Now));
    }

    public void Dispose() => home.Dispose();

    private Heartbeats TheHeartbeats() => new(new JidokaHome(home.Path));

    private void Write(string epic, string content)
    {
        var folder = home.CreateSubdirectory("heartbeat");
        File.WriteAllText(Path.Combine(folder, $"{epic}.json"), content);
    }
}
