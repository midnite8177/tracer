using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Beads;

public sealed class BdConcurrencyTests
{
    private static readonly DateTimeOffset Start = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

    private static ProjectPath ProjectNumber(int number) =>
        ProjectPath.From(Path.Combine(Path.GetTempPath(), $"project-{number}"));

    [Fact]
    public async Task RunsNoMoreBdCallsAtOnceThanTheLimitWhenEveryProjectReadsAtTheSameMoment()
    {
        var bd = new BdThatCountsRunsAtOnce(() => Task.Delay(TimeSpan.FromMilliseconds(15)));
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var reads = Enumerable.Range(0, 8)
            .SelectMany(number => new[]
            {
                adapter.ListAsync(ProjectNumber(number)),
                adapter.ReadyAsync(ProjectNumber(number)),
                adapter.BlockedAsync(ProjectNumber(number)),
            })
            .ToArray();
        var outcomes = await Task.WhenAll(reads);

        Assert.All(outcomes, outcome => Assert.True(outcome.Answered));
        Assert.Equal(24, bd.Started);
        Assert.Equal(BdAdapter.RunsAtOnce, bd.MostAtOnce);
    }

    [Fact]
    public async Task KeepsThePlaceOfARunThatTheAppGaveUpOnUntilItsProcessEnds()
    {
        var bd = new FakeBd().Holds("ready --json").Prints("blocked --json", "[]");
        var clock = new FakeTimeProvider(Start);
        var adapter = new BdAdapter(bd, clock);

        var held = Enumerable.Range(0, BdAdapter.RunsAtOnce)
            .Select(number => adapter.ReadyAsync(ProjectNumber(number)))
            .ToArray();
        var queued = adapter.BlockedAsync(ProjectNumber(BdAdapter.RunsAtOnce));

        clock.Advance(BdAdapter.WaitLimit);
        var outcomes = await Task.WhenAll(held);

        Assert.All(outcomes, outcome => Assert.True(outcome.GaveUp));
        Assert.False(queued.IsCompleted);
        Assert.DoesNotContain("blocked --json", bd.Invocations);

        bd.Answers("ready --json", "[]");
        var answer = await queued;

        Assert.True(answer.Answered);
    }

    [Fact]
    public async Task NeverHasMoreBdProcessesAliveThanTheLimitWhenRunsOutwaitTheirLimit()
    {
        var gate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var bd = new BdThatCountsRunsAtOnce(() => gate.Task);
        var clock = new FakeTimeProvider(Start);
        var adapter = new BdAdapter(bd, clock);

        var calls = Enumerable.Range(0, BdAdapter.RunsAtOnce * 2)
            .Select(number => adapter.ReadyAsync(ProjectNumber(number)))
            .ToArray();
        var first = calls.Take(BdAdapter.RunsAtOnce).ToArray();

        clock.Advance(BdAdapter.WaitLimit);
        var gaveUp = await Task.WhenAll(first);

        Assert.All(gaveUp, outcome => Assert.True(outcome.GaveUp));
        Assert.Equal(BdAdapter.RunsAtOnce, bd.Started);

        gate.SetResult();
        await Task.WhenAll(calls);

        Assert.Equal(BdAdapter.RunsAtOnce * 2, bd.Started);
        Assert.Equal(BdAdapter.RunsAtOnce, bd.MostAtOnce);
    }

    [Fact]
    public async Task DoesNotCountTheTimeACallWaitsInTheQueueAgainstItsWaitLimit()
    {
        var bd = new FakeBd().Holds("ready --json").Prints("blocked --json", "[]");
        var clock = new FakeTimeProvider(Start);
        var adapter = new BdAdapter(bd, clock);

        var held = Enumerable.Range(0, BdAdapter.RunsAtOnce)
            .Select(number => adapter.ReadyAsync(ProjectNumber(number)))
            .ToArray();
        var queued = adapter.BlockedAsync(ProjectNumber(BdAdapter.RunsAtOnce));

        clock.Advance(BdAdapter.WaitLimit - TimeSpan.FromSeconds(1));
        Assert.False(queued.IsCompleted);
        bd.Answers("ready --json", "[]");
        await Task.WhenAll(held);
        var answer = await queued;

        Assert.True(answer.Answered);
        Assert.False(answer.GaveUp);
    }
}
