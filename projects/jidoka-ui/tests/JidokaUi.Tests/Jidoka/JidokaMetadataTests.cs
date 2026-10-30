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

        Assert.Equal(("2", "build", "1"), (lap.Number, lap.Stage, lap.TriesAtStage));
    }

    [Fact]
    public async Task ReadsTheTriesAndTheCapOfTheLapsOwnCountAtAnyStageButTheMerge()
    {
        var bead = await TheBead("""
            "metadata": {"lap.stage": "build", "lap.tries": 1, "lap.trycap": 5, "lap.mergetries": 3, "lap.mergetrycap": 4}
            """);

        var lap = JidokaMetadata.LapOn(bead);

        Assert.Equal(("1", "5"), (lap.TriesAtStage, lap.CapAtStage));
    }

    [Fact]
    public async Task ReadsTheTriesAndTheCapOfTheMergeCountAtTheMergeStage()
    {
        var bead = await TheBead("""
            "metadata": {"lap.stage": "merge", "lap.tries": 1, "lap.trycap": 5, "lap.mergetries": 3, "lap.mergetrycap": 4}
            """);

        var lap = JidokaMetadata.LapOn(bead);

        Assert.Equal(("3", "4"), (lap.TriesAtStage, lap.CapAtStage));
    }

    [Fact]
    public async Task ReadsEveryPartOfTheLapAsEmptyWhenTheTaskNeverHeldOne()
    {
        var bead = await TheBead("\"metadata\": {}");

        var lap = JidokaMetadata.LapOn(bead);

        Assert.Equal(string.Empty, lap.Number + lap.Stage + lap.TriesAtStage + lap.CapAtStage);
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
    public async Task ReadsTheEventsThatTheNotifyScriptRecordedWithTheBeadTheTitleAndTheTextOfEach()
    {
        var bead = await TheBead("""
            "metadata": {"notification": {
              "task-parked:a.1": {"fingerprint": "f1", "title": "Task parked: Read the header", "text": "Pick a format."},
              "acceptance-gate:a": {"fingerprint": "f2", "title": "Ready for acceptance: The parser", "text": "Merge it or drop it, or send it back with /jidoka:accept."}}}
            """);

        Assert.Equal(
            [
                new RecordedEvent("task-parked", "a.1", "f1", "Task parked: Read the header", "Pick a format."),
                new RecordedEvent("acceptance-gate", "a", "f2", "Ready for acceptance: The parser", "Merge it or drop it, or send it back with /jidoka:accept."),
            ],
            JidokaMetadata.EventsOn(bead));
    }

    [Fact]
    public async Task ReadsTheEventsWhenBdPrintsTheRecordAsTheTextOfAnObject()
    {
        var bead = await TheBead("""
            "metadata": {"notification": "{\"epic-parked:a\": {\"fingerprint\": \"f1\", \"title\": \"T\", \"text\": \"X\"}}"}
            """);

        Assert.Equal([new RecordedEvent("epic-parked", "a", "f1", "T", "X")], JidokaMetadata.EventsOn(bead));
    }

    [Fact]
    public async Task ReadsTheFingerprintOfAnEventThatIsNotTextAsTheJsonItHolds()
    {
        var bead = await TheBead("""
            "metadata": {"notification": {"task-parked:a.1": {"fingerprint": 7, "title": "T", "text": "X"}}}
            """);

        Assert.Equal([new RecordedEvent("task-parked", "a.1", "7", "T", "X")], JidokaMetadata.EventsOn(bead));
    }

    [Theory]
    [InlineData("\"f1\"")]
    [InlineData("{\"fingerprint\": \"f1\", \"text\": \"X\"}")]
    [InlineData("{\"fingerprint\": \"f1\", \"title\": \"\", \"text\": \"X\"}")]
    [InlineData("{\"title\": \"T\", \"text\": \"X\"}")]
    public async Task LeavesOutAnEntryThatIsNoObjectWithAFingerprintAndATitle(string entry)
    {
        var bead = await TheBead($$$"""
            "metadata": {"notification": {"task-parked:a.1": {{{entry}}}}}
            """);

        Assert.Empty(JidokaMetadata.EventsOn(bead));
    }

    [Fact]
    public async Task ReadsTheTextOfAnEntryThatHoldsNoneAsEmpty()
    {
        var bead = await TheBead("""
            "metadata": {"notification": {"task-parked:a.1": {"fingerprint": "f1", "title": "T"}}}
            """);

        Assert.Equal([new RecordedEvent("task-parked", "a.1", "f1", "T", string.Empty)], JidokaMetadata.EventsOn(bead));
    }

    [Theory]
    [InlineData("no colon")]
    [InlineData(":a")]
    [InlineData("task-parked:")]
    public async Task LeavesOutAnEntryWhoseNameDoesNotSplitIntoAnEventAndABead(string name)
    {
        var bead = await TheBead($$$$"""
            "metadata": {"notification": {"{{{{name}}}}": {"fingerprint": "f1", "title": "T", "text": "X"}}}
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
