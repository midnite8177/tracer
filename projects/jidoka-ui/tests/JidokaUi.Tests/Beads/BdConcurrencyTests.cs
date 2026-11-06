using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Beads;

public sealed class BdConcurrencyTests
{
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
        Assert.Equal(BdRunGate.RunsAtOnce, bd.MostAtOnce);
    }
}
