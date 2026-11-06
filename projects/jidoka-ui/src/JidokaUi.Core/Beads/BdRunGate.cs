namespace JidokaUi.Core.Beads;

/// <summary>
/// The one gate that every bd process of the app passes through. It holds the places that limit how
/// many run at once, and it applies the <see cref="BdAdapter.WaitLimit"/> after which the app gives
/// up on an answer, so the command layer above it never schedules a process itself. A run that outran
/// the limit keeps its place among <see cref="RunsAtOnce"/> until its process ends, which
/// <see cref="GivingUp"/> decides whether the app brings about.
/// </summary>
internal sealed class BdRunGate
{
    /// <summary>
    /// The most bd processes that the gate has running at once. Each one opens the database of its
    /// project, and many together slow one another and every other program that calls bd. A run
    /// holds its place until its process ends, also after the app stopped waiting for its answer,
    /// so a call past the limit queues until a process ends. The adapter owns every bd invocation
    /// of the app and holds one gate, so the limit holds across every project. It does not count
    /// the bd calls that the scripts of jidoka make.
    /// </summary>
    public const int RunsAtOnce = 3;

    private readonly SemaphoreSlim places = new(RunsAtOnce, RunsAtOnce);
    private readonly IBdProcess process;
    private readonly TimeProvider clock;

    public BdRunGate(IBdProcess process, TimeProvider clock)
    {
        this.process = process;
        this.clock = clock;
    }

    /// <summary>
    /// Runs bd once in the directory and returns what it gave back, or null when the app gave up
    /// waiting. The gate waits for a place first and starts the clock after, so the time in the
    /// queue never counts against <see cref="BdAdapter.WaitLimit"/>. A run that the gate gave up on keeps its
    /// place until its process ends, because a freed place would let another start beside it. When
    /// <paramref name="givingUp"/> stops the process, that end comes at once.
    /// </summary>
    public async Task<BdResult?> RunOrGiveUpAsync(
        string workingDirectory, IReadOnlyList<string> arguments, GivingUp givingUp)
    {
        await places.WaitAsync();
        using var stop = new CancellationTokenSource();
        var run = RunAndFreeThePlaceAsync(
            workingDirectory, arguments, givingUp == GivingUp.StopsTheProcess ? stop.Token : CancellationToken.None);
        var winner = await Task.WhenAny(run, Task.Delay(BdAdapter.WaitLimit, clock));
        if (winner == run)
        {
            return await run;
        }

        await stop.CancelAsync();
        return null;
    }

    private async Task<BdResult> RunAndFreeThePlaceAsync(
        string workingDirectory,
        IReadOnlyList<string> arguments,
        CancellationToken stop)
    {
        try
        {
            return await process.RunAsync(workingDirectory, arguments, stop);
        }
        finally
        {
            places.Release();
        }
    }
}

/// <summary>
/// What the gate does with a bd process whose answer the app gave up on. A read is stopped, because
/// a run left going keeps the database of its project busy. A write is left to finish, because a
/// write stopped midway could leave a bead half changed, and the app tells the person that it may
/// still land.
/// </summary>
internal enum GivingUp
{
    StopsTheProcess,
    LeavesTheProcessRunning,
}
