using JidokaUi.Core.Beads;

namespace JidokaUi.Tests.Beads;

public sealed class BdRunGateTests
{
    private static readonly DateTimeOffset Start = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

    private static readonly string[] Ready = ["ready", "--json"];
    private static readonly string[] Blocked = ["blocked", "--json"];

    private static string DirectoryNumber(int number) =>
        Path.Combine(Path.GetTempPath(), $"project-{number}");

    [Fact]
    public async Task ReturnsWhatBdAnsweredWhenItAnswersWithinTheWaitLimit()
    {
        var bd = new FakeBd().Prints("ready --json", "[1]");
        var gate = new BdRunGate(bd, new FakeTimeProvider(Start));

        var result = await gate.RunOrGiveUpAsync(DirectoryNumber(0), Ready);

        Assert.NotNull(result);
        Assert.Equal("[1]", result.StandardOutput);
    }

    [Fact]
    public async Task ReturnsNothingForARunThatOutrunsTheWaitLimit()
    {
        var bd = new FakeBd().Holds("ready --json");
        var clock = new FakeTimeProvider(Start);
        var gate = new BdRunGate(bd, clock);

        var running = gate.RunOrGiveUpAsync(DirectoryNumber(0), Ready);
        clock.Advance(BdRunGate.WaitLimit);

        Assert.Null(await running);
    }

    [Fact]
    public async Task RunsNoMoreProcessesAtOnceThanTheLimit()
    {
        var bd = new BdThatCountsRunsAtOnce(() => Task.Delay(TimeSpan.FromMilliseconds(15)));
        var gate = new BdRunGate(bd, TimeProvider.System);

        var runs = Enumerable.Range(0, 24)
            .Select(number => gate.RunOrGiveUpAsync(DirectoryNumber(number), Ready))
            .ToArray();
        var results = await Task.WhenAll(runs);

        Assert.All(results, result => Assert.NotNull(result));
        Assert.Equal(24, bd.Started);
        Assert.Equal(BdRunGate.RunsAtOnce, bd.MostAtOnce);
    }

    [Fact]
    public async Task KeepsThePlaceOfARunThatItGaveUpOnUntilItsProcessEnds()
    {
        var bd = new FakeBd().Holds("ready --json").Prints("blocked --json", "[]");
        var clock = new FakeTimeProvider(Start);
        var gate = new BdRunGate(bd, clock);

        var held = Enumerable.Range(0, BdRunGate.RunsAtOnce)
            .Select(number => gate.RunOrGiveUpAsync(DirectoryNumber(number), Ready))
            .ToArray();
        var queued = gate.RunOrGiveUpAsync(DirectoryNumber(BdRunGate.RunsAtOnce), Blocked);

        clock.Advance(BdRunGate.WaitLimit);
        var results = await Task.WhenAll(held);

        Assert.All(results, result => Assert.Null(result));
        Assert.False(queued.IsCompleted);
        Assert.DoesNotContain("blocked --json", bd.Invocations);

        bd.Answers("ready --json", "[]");
        var answer = await queued;

        Assert.NotNull(answer);
    }

    [Fact]
    public async Task NeverHasMoreProcessesAliveThanTheLimitWhenRunsOutwaitTheirLimit()
    {
        var processEnds = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var bd = new BdThatCountsRunsAtOnce(() => processEnds.Task);
        var clock = new FakeTimeProvider(Start);
        var gate = new BdRunGate(bd, clock);

        var calls = Enumerable.Range(0, BdRunGate.RunsAtOnce * 2)
            .Select(number => gate.RunOrGiveUpAsync(DirectoryNumber(number), Ready))
            .ToArray();
        var first = calls.Take(BdRunGate.RunsAtOnce).ToArray();

        clock.Advance(BdRunGate.WaitLimit);
        var gaveUp = await Task.WhenAll(first);

        Assert.All(gaveUp, result => Assert.Null(result));
        Assert.Equal(BdRunGate.RunsAtOnce, bd.Started);

        processEnds.SetResult();
        await Task.WhenAll(calls);

        Assert.Equal(BdRunGate.RunsAtOnce * 2, bd.Started);
        Assert.Equal(BdRunGate.RunsAtOnce, bd.MostAtOnce);
    }

    [Fact]
    public async Task DoesNotCountTheTimeARunWaitsForAPlaceAgainstItsWaitLimit()
    {
        var bd = new FakeBd().Holds("ready --json").Prints("blocked --json", "[]");
        var clock = new FakeTimeProvider(Start);
        var gate = new BdRunGate(bd, clock);

        var held = Enumerable.Range(0, BdRunGate.RunsAtOnce)
            .Select(number => gate.RunOrGiveUpAsync(DirectoryNumber(number), Ready))
            .ToArray();
        var queued = gate.RunOrGiveUpAsync(DirectoryNumber(BdRunGate.RunsAtOnce), Blocked);

        clock.Advance(BdRunGate.WaitLimit - TimeSpan.FromSeconds(1));
        Assert.False(queued.IsCompleted);
        bd.Answers("ready --json", "[]");
        await Task.WhenAll(held);
        var answer = await queued;

        Assert.NotNull(answer);
    }
}
