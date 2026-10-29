using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;

namespace JidokaUi.Tests.Jidoka;

public sealed class JidokaMetadataTests : IDisposable
{
    private readonly TempDirectory directory = new();

    public void Dispose() => directory.Dispose();

    [Fact]
    public async Task ReadsTheLapThatTheSchedulerRecordedOnATask()
    {
        var bead = await TheBead("""
            "metadata": {"lap.number": 2, "lap.stage": "build", "lap.tries": 1, "lap.mergetries": 0}
            """);

        var lap = JidokaMetadata.LapOn(bead);

        Assert.Equal(("2", "build", "1", "0"), (lap.Number, lap.Stage, lap.Tries, lap.MergeTries));
    }

    [Fact]
    public async Task ReadsEveryPartOfTheLapAsEmptyWhenTheTaskNeverHeldOne()
    {
        var bead = await TheBead("\"metadata\": {}");

        var lap = JidokaMetadata.LapOn(bead);

        Assert.Equal(string.Empty, lap.Number + lap.Stage + lap.Tries + lap.MergeTries);
    }

    [Fact]
    public async Task ReadsAnEpicThatWaitsAtTheGateFromTheGateState()
    {
        var bead = await TheBead("""
            "metadata": {"gate.state": "waiting"}
            """);

        Assert.Equal(GateState.Waiting, JidokaMetadata.GateStateOn(bead));
    }

    [Theory]
    [InlineData("merged")]
    [InlineData("")]
    public async Task ReadsAnyOtherGateStateAsNotWaiting(string state)
    {
        var bead = await TheBead($$"""
            "metadata": {"gate.state": "{{state}}"}
            """);

        Assert.Equal(GateState.NotWaiting, JidokaMetadata.GateStateOn(bead));
    }

    [Fact]
    public async Task ReadsNoGateStateAsNotWaiting()
    {
        var bead = await TheBead("\"metadata\": {}");

        Assert.Equal(GateState.NotWaiting, JidokaMetadata.GateStateOn(bead));
    }

    [Fact]
    public async Task ReadsTheEventsThatTheNotifyScriptRecordedWithTheBeadOfEach()
    {
        var bead = await TheBead("""
            "metadata": {"notification": {"task-parked:a.1": "f1", "acceptance-gate:a": "f2"}}
            """);

        Assert.Equal(
            [new RecordedEvent("task-parked", "a.1", "f1"), new RecordedEvent("acceptance-gate", "a", "f2")],
            JidokaMetadata.EventsOn(bead));
    }

    [Fact]
    public async Task ReadsTheEventsWhenBdPrintsTheRecordAsTheTextOfAnObject()
    {
        var bead = await TheBead("""
            "metadata": {"notification": "{\"epic-parked:a\": \"f1\"}"}
            """);

        Assert.Equal([new RecordedEvent("epic-parked", "a", "f1")], JidokaMetadata.EventsOn(bead));
    }

    [Fact]
    public async Task ReadsTheFingerprintOfAnEventThatIsNotTextAsTheJsonItHolds()
    {
        var bead = await TheBead("""
            "metadata": {"notification": {"task-parked:a.1": 7}}
            """);

        Assert.Equal([new RecordedEvent("task-parked", "a.1", "7")], JidokaMetadata.EventsOn(bead));
    }

    [Theory]
    [InlineData("no colon")]
    [InlineData(":a")]
    [InlineData("task-parked:")]
    public async Task LeavesOutAnEntryWhoseNameDoesNotSplitIntoAnEventAndABead(string name)
    {
        var bead = await TheBead($$"""
            "metadata": {"notification": "{\"{{name}}\": \"f1\"}"}
            """);

        Assert.Empty(JidokaMetadata.EventsOn(bead));
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("[]")]
    [InlineData("7")]
    public async Task ReadsNoEventsFromARecordThatIsNotAnObject(string record)
    {
        var bead = await TheBead($$"""
            "metadata": {"notification": "{{record}}"}
            """);

        Assert.Empty(JidokaMetadata.EventsOn(bead));
    }

    [Fact]
    public async Task ReadsNoEventsFromABeadThatRecordedNone()
    {
        var bead = await TheBead("\"metadata\": {}");

        Assert.Empty(JidokaMetadata.EventsOn(bead));
    }

    private async Task<Bead> TheBead(string field)
    {
        var project = ProjectPath.From(directory.CreateSubdirectory("project"));
        var bd = new FakeBd()
            .PrintsIn(
                project.Value,
                "list --all --limit 0 --json",
                $$"""[{"id": "b-7", "title": "Pick a hosting plan", "labels": ["human"], {{field}} }]""")
            .Prints("ready --json", "[]")
            .Prints("blocked --json", "[]");

        var outcome = await new BacklogReader(new BdAdapter(bd, TimeProvider.System)).ReadAsync(project);

        Assert.True(outcome.Answered);
        return Assert.Single(outcome.Backlog.Beads);
    }
}
