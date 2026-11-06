namespace JidokaUi.Core.Beads;

/// <summary>
/// The one gate that every bd process of the app passes through. It holds the places that limit how
/// many run at once and the wait limit after which the app gives up on an answer, so the command
/// layer above it never schedules a process itself.
/// </summary>
internal sealed class BdRunGate
{
    /// <summary>
    /// How long a run waits for bd before the app gives up on it. The app cannot stop bd itself, so
    /// a run that outran this is not claimed to have been stopped, and it keeps its place among
    /// <see cref="RunsAtOnce"/> until its process ends.
    /// </summary>
    public static readonly TimeSpan WaitLimit = TimeSpan.FromSeconds(30);

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
    /// queue never counts against <see cref="WaitLimit"/>. A run that the gate gave up on keeps its
    /// place until its process ends, because the app cannot stop that process and a freed place
    /// would let another start beside it.
    /// </summary>
    public async Task<BdResult?> RunOrGiveUpAsync(string workingDirectory, IReadOnlyList<string> arguments)
    {
        await places.WaitAsync();
        var run = RunAndFreeThePlaceAsync(workingDirectory, arguments);
        var winner = await Task.WhenAny(run, Task.Delay(WaitLimit, clock));
        return winner == run ? await run : null;
    }

    private async Task<BdResult> RunAndFreeThePlaceAsync(
        string workingDirectory,
        IReadOnlyList<string> arguments)
    {
        try
        {
            return await process.RunAsync(workingDirectory, arguments);
        }
        finally
        {
            places.Release();
        }
    }
}
