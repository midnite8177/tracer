using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Factory;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Notifications;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;
using JidokaUi.Tests.Boards;
using JidokaUi.Tests.Projects;

namespace JidokaUi.Tests.Notifications;

public sealed class FactoryWatchTests : IDisposable
{
    private const string ListCommand = "list --all --limit 0 --json";

    private readonly TempDirectory directory = new();
    private readonly ProjectPath atHome;
    private readonly ProjectPath atWork;
    private readonly FakeBd bd = new FakeBd().Prints("ready --json", "[]").Prints("blocked --json", "[]");
    private readonly FakeTimeProvider clock = new(new DateTimeOffset(2026, 1, 1, 12, 0, 0, TimeSpan.Zero));
    private readonly BacklogCache backlogs;
    private readonly FactoryWatch watch;
    private readonly List<BrowserNotification> raised = [];

    public FactoryWatchTests()
    {
        atHome = ProjectPath.From(directory.CreateSubdirectory("home-project"));
        atWork = ProjectPath.From(directory.CreateSubdirectory("work-project"));
        var store = new InMemoryProjectRegistryStore();
        store.Hold(new ProjectRegistry([atHome, atWork], []));
        var adapter = new BdAdapter(bd, clock);
        backlogs = new BacklogCache(new BacklogReader(adapter), adapter);
        var catalog = new ProjectCatalog(store, adapter, new NoOnboardedProjects());
        watch = new FactoryWatch(
            new FactoryReader(catalog, backlogs),
            catalog,
            backlogs,
            new ProjectWatchers(backlogs, new FakeWriteReports()),
            new Heartbeats(new JidokaHome(directory.CreateSubdirectory("jidoka-home"))),
            clock);
        watch.Raised += raised.Add;
        Lists(atHome, "[]");
        Lists(atWork, "[]");
    }

    [Fact]
    public async Task RaisesNothingForWhatTheEpicRecordedBeforeTheAppFirstReadTheProject()
    {
        Lists(atHome, ParkedTask("f1"));

        await watch.CheckAsync();

        Assert.Empty(raised);
    }

    [Fact]
    public async Task RaisesOneNotificationThatOpensTheTaskWhenATaskIsParked()
    {
        await watch.CheckAsync();

        Lists(atHome, ParkedTask("f1"));
        await watch.CheckAsync();

        var parked = Assert.Single(raised);
        Assert.Equal("Task parked: Read the header", parked.Title);
        Assert.Equal(
            $"bead/a.1?project={Uri.EscapeDataString(atHome.Value)}",
            parked.Address);
    }

    [Fact]
    public async Task ShowsTheHeadlineAndTheSentenceThatJidokaRecordedWhateverTheyAre()
    {
        await watch.CheckAsync();

        Lists(atHome, EpicThatRecorded($$"""{"task-parked:a.1": {{Entry("f1", "Wording from jidoka", "Its own sentence.")}}}"""));
        await watch.CheckAsync();

        var notification = Assert.Single(raised);
        Assert.Equal(("Wording from jidoka", "Its own sentence."), (notification.Title, notification.Body));
    }

    [Fact]
    public async Task RaisesAnEventOnceHoweverOftenTheProjectIsReadAgain()
    {
        await watch.CheckAsync();
        Lists(atHome, ParkedTask("f1"));

        await watch.CheckAsync();
        Lists(atHome, ParkedTask("f1"));
        await watch.CheckAsync();
        await watch.CheckAsync();

        Assert.Single(raised);
    }

    [Fact]
    public async Task RaisesTheEventAgainWhenTheTaskIsParkedAgainUnderANewFingerprint()
    {
        await watch.CheckAsync();
        Lists(atHome, ParkedTask("f1"));
        await watch.CheckAsync();

        Lists(atHome, ParkedTask("f2"));
        await watch.CheckAsync();

        Assert.Equal(2, raised.Count);
        Assert.NotEqual(raised[0].Tag, raised[1].Tag);
    }

    [Fact]
    public async Task RaisesTheEventsOfEveryProjectOfTheRegistry()
    {
        await watch.CheckAsync();

        Lists(atHome, ParkedTask("f1"));
        Lists(atWork, EpicThatRecorded($$"""{"acceptance-gate:a": {{Entry("g1", "Ready for acceptance: The parser", "Merge it.")}}}"""));
        await watch.CheckAsync();

        Assert.Equal(
            ["Ready for acceptance: The parser", "Task parked: Read the header"],
            raised.Select(notification => notification.Title).Order(StringComparer.Ordinal));
    }

    [Fact]
    public async Task RaisesWhenTheProjectChangesWithoutBeingAsked()
    {
        var found = new TaskCompletionSource<BrowserNotification>(TaskCreationOptions.RunContinuationsAsynchronously);
        watch.Raised += notification => found.TrySetResult(notification);
        await watch.CheckAsync();
        watch.Start();

        Lists(atHome, ParkedTask("f1"));

        Assert.Equal("Task parked: Read the header", (await found.Task.WaitAsync(TimeSpan.FromSeconds(10))).Title);
    }

    [Fact]
    public async Task WarnsOnceWhenTheHeartbeatOfARunningEpicTurnsStale()
    {
        Lists(atHome, RunningEpic());
        BeatsNow("a", 90);
        await watch.CheckAsync();

        clock.Advance(TimeSpan.FromSeconds(91));
        await watch.CheckAsync();
        clock.Advance(TimeSpan.FromSeconds(30));
        await watch.CheckAsync();

        var warning = Assert.Single(raised);
        Assert.Equal("Heartbeat stale: The parser", warning.Title);
        Assert.Equal($"bead/a?project={Uri.EscapeDataString(atHome.Value)}", warning.Address);
    }

    [Fact]
    public async Task WarnsWhenTheHeartbeatIsOlderThanTheLimitItsFileNamesWhateverThatLimitIs()
    {
        Lists(atHome, RunningEpic());
        BeatsNow("a", 20);
        await watch.CheckAsync();

        clock.Advance(TimeSpan.FromSeconds(21));
        await watch.CheckAsync();

        Assert.Equal("Heartbeat stale: The parser", Assert.Single(raised).Title);
    }

    [Fact]
    public async Task WarnsAgainInTheNextStaleSpellAfterTheHeartbeatWasFresh()
    {
        Lists(atHome, RunningEpic());
        BeatsNow("a", 90);
        await watch.CheckAsync();
        clock.Advance(TimeSpan.FromSeconds(91));
        await watch.CheckAsync();

        BeatsNow("a", 90);
        await watch.CheckAsync();
        clock.Advance(TimeSpan.FromSeconds(91));
        await watch.CheckAsync();

        Assert.Equal(2, raised.Count);
        Assert.NotEqual(raised[0].Tag, raised[1].Tag);
    }

    [Fact]
    public async Task WarnsOfNothingWhileTheHeartbeatIsNoOlderThanAMinuteAndAHalf()
    {
        Lists(atHome, RunningEpic());
        BeatsNow("a", 90);
        await watch.CheckAsync();

        clock.Advance(TimeSpan.FromSeconds(90));
        await watch.CheckAsync();

        Assert.Empty(raised);
    }

    [Fact]
    public async Task WarnsOfNothingForARunningEpicThatHasNoHeartbeat()
    {
        Lists(atHome, RunningEpic());
        await watch.CheckAsync();

        clock.Advance(TimeSpan.FromMinutes(10));
        await watch.CheckAsync();

        Assert.Empty(raised);
    }

    [Theory]
    [InlineData("""["factory", "human"]""", "{}")]
    [InlineData("""["factory"]""", """{"gate.state": "waiting"}""")]
    public async Task WarnsOfNothingForAnEpicThatAPersonOrTheGateHolds(string labels, string metadata)
    {
        Lists(atHome, $$"""[{"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": {{labels}}, "metadata": {{metadata}}}]""");
        BeatsNow("a", 90);
        await watch.CheckAsync();

        clock.Advance(TimeSpan.FromMinutes(10));
        await watch.CheckAsync();

        Assert.Empty(raised);
    }

    [Fact]
    public async Task WarnsOfNothingForAHeartbeatThatWasStaleBeforeTheAppFirstReadTheProject()
    {
        Lists(atHome, RunningEpic());
        BeatsNow("a", 90);
        clock.Advance(TimeSpan.FromMinutes(10));

        await watch.CheckAsync();
        await watch.CheckAsync();

        Assert.Empty(raised);
    }

    [Fact]
    public async Task ChecksTheHeartbeatsOnTheClockWithoutBeingAsked()
    {
        var warned = new TaskCompletionSource<BrowserNotification>(TaskCreationOptions.RunContinuationsAsynchronously);
        watch.Raised += notification => warned.TrySetResult(notification);
        Lists(atHome, RunningEpic());
        BeatsNow("a", 90);
        await watch.CheckAsync();
        watch.Start();

        clock.Advance(TimeSpan.FromSeconds(91));

        Assert.Equal("Heartbeat stale: The parser", (await warned.Task.WaitAsync(TimeSpan.FromSeconds(10))).Title);
    }

    public void Dispose()
    {
        watch.Dispose();
        directory.Dispose();
    }

    private void Lists(ProjectPath project, string json)
    {
        bd.PrintsIn(project.Value, ListCommand, json);
        backlogs.InvalidateFromWatch(project);
    }

    private void BeatsNow(string epic, int freshSeconds)
    {
        var folder = Path.Combine(directory.Path, "jidoka-home", "heartbeat");
        Directory.CreateDirectory(folder);
        File.WriteAllText(
            Path.Combine(folder, $"{epic}.json"),
            $$"""
            {"epic": "{{epic}}", "time": {{clock.GetUtcNow().ToUnixTimeSeconds()}}, "session": null, "fresh_seconds": {{freshSeconds}}}
            """);
    }

    private static string Entry(string fingerprint, string title, string text) =>
        $$"""{"fingerprint": "{{fingerprint}}", "title": "{{title}}", "text": "{{text}}"}""";

    private static string RunningEpic() =>
        """[{"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": ["factory"]}]""";

    private static string ParkedTask(string fingerprint) =>
        $$$"""
        [
          {"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": ["factory"],
           "metadata": {"notification": {"task-parked:a.1": {{{Entry(fingerprint, "Task parked: Read the header", "The task waits on you.")}}} } } },
          {"id": "a.1", "title": "Read the header", "issue_type": "task", "status": "open", "parent": "a",
           "labels": ["human"]}
        ]
        """;

    private static string EpicThatRecorded(string notification) =>
        $$$"""
        [
          {"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": ["factory"],
           "metadata": {"notification": {{{notification}}} } },
          {"id": "a.1", "title": "Read the header", "issue_type": "task", "status": "open", "parent": "a"}
        ]
        """;
}
