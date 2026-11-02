using JidokaUi.Core.Beads;

namespace JidokaUi.Tests.Beads;

/// <summary>
/// A bd that answers every command with an empty JSON array once the wait it was given ends, and
/// records the most runs that were under way at the same moment, so a run that the app stopped
/// waiting on still counts until its wait ends.
/// </summary>
public sealed class BdThatCountsRunsAtOnce : IBdProcess
{
    private readonly Func<Task> untilItAnswers;
    private int underWay;
    private int mostUnderWay;
    private int started;

    public BdThatCountsRunsAtOnce(Func<Task> untilItAnswers)
    {
        this.untilItAnswers = untilItAnswers;
    }

    public int MostAtOnce => Volatile.Read(ref mostUnderWay);

    public int Started => Volatile.Read(ref started);

    public async Task<BdResult> RunAsync(string workingDirectory, IReadOnlyList<string> arguments)
    {
        Interlocked.Increment(ref started);
        var now = Interlocked.Increment(ref underWay);
        RaiseTheMostTo(now);
        try
        {
            await untilItAnswers();
            return new BdResult(0, "[]", string.Empty);
        }
        finally
        {
            Interlocked.Decrement(ref underWay);
        }
    }

    private void RaiseTheMostTo(int now)
    {
        int seen;
        do
        {
            seen = Volatile.Read(ref mostUnderWay);
        }
        while (now > seen && Interlocked.CompareExchange(ref mostUnderWay, now, seen) != seen);
    }
}
