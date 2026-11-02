using JidokaUi.Core.Beads;
using JidokaUi.Core.Jidoka;

namespace JidokaUi.Tests.Jidoka;

/// <summary>
/// The program that starts jidoka's scripts, written by hand. It answers a scripted exit code and
/// scripted streams for each command line, where the command line is the name of the script followed
/// by its arguments, and it leaves out the home flag that every run ends with, so a test reads
/// <c>gate.py drop b-1</c>. It can also change another fake when a script runs, as a script changes
/// the bead that a later read gives back, and hold one command line open.
/// </summary>
public sealed class FakeJidoka : IJidokaProcess
{
    private const string HomeFlag = "--jidoka-home=";

    private readonly Dictionary<string, BdResult> scripted = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Action> changes = new(StringComparer.Ordinal);
    private readonly Dictionary<string, TaskCompletionSource<BdResult>> held = new(StringComparer.Ordinal);

    private int running;
    private int mostAtOnce;

    /// <summary>The command lines that the code under test ran, in order.</summary>
    public List<string> Invocations { get; } = [];

    public int MostRunsAtOnce => Volatile.Read(ref mostAtOnce);

    /// <summary>The program of each run, in order.</summary>
    public List<string> Programs { get; } = [];

    /// <summary>The directory of each run, in order.</summary>
    public List<string> Directories { get; } = [];

    /// <summary>The home that each run named, in order.</summary>
    public List<string> Homes { get; } = [];

    /// <summary>The token of each run, in order, which the code under test cancels to stop that run.</summary>
    public List<CancellationToken> Stops { get; } = [];

    /// <summary>Scripts a run that exits with success and prints this.</summary>
    public FakeJidoka Prints(string commandLine, string standardOutput) =>
        Exits(commandLine, 0, standardOutput, string.Empty);

    /// <summary>Scripts a run that exits with 1 and says this on its error stream, as a refusal does.</summary>
    public FakeJidoka Fails(string commandLine, string standardError) =>
        Exits(commandLine, 1, string.Empty, standardError);

    /// <summary>Scripts a run that exits with this code and these streams.</summary>
    public FakeJidoka Exits(string commandLine, int exitCode, string standardOutput, string standardError)
    {
        scripted[commandLine] = new BdResult(exitCode, standardOutput, standardError);
        return this;
    }

    /// <summary>Runs this change when a run of the command line starts, as the script changes the beads.</summary>
    public FakeJidoka After(string commandLine, Action change)
    {
        changes[commandLine] = change;
        return this;
    }

    /// <summary>Holds every run of this command line open until <see cref="Answers"/>.</summary>
    public FakeJidoka Holds(string commandLine)
    {
        held[commandLine] = new TaskCompletionSource<BdResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        return this;
    }

    /// <summary>Answers the runs that <see cref="Holds"/> holds open, with success and this output.</summary>
    public FakeJidoka Answers(string commandLine, string standardOutput)
    {
        if (!held.Remove(commandLine, out var holding))
        {
            throw new InvalidOperationException($"\"{commandLine}\" is not a held run. Call Holds before Answers.");
        }

        holding.SetResult(new BdResult(0, standardOutput, string.Empty));
        return this;
    }

    public Task<BdResult> RunAsync(
        string program, string workingDirectory, IReadOnlyList<string> arguments, CancellationToken stop)
    {
        var home = arguments.Where(argument => argument.StartsWith(HomeFlag, StringComparison.Ordinal)).ToList();
        var rest = arguments.Where(argument => !argument.StartsWith(HomeFlag, StringComparison.Ordinal)).ToList();
        var commandLine = string.Join(' ', [Path.GetFileName(rest[0]), .. rest.Skip(1)]);
        Invocations.Add(commandLine);
        Programs.Add(program);
        Directories.Add(workingDirectory);
        Homes.AddRange(home.Select(flag => flag[HomeFlag.Length..]));
        Stops.Add(stop);
        InterlockedMax(ref mostAtOnce, Interlocked.Increment(ref running));
        return DropsFromTheCountAsItEnds(Answer(commandLine));
    }

    private async Task<BdResult> DropsFromTheCountAsItEnds(Task<BdResult> run)
    {
        try
        {
            return await run;
        }
        finally
        {
            Interlocked.Decrement(ref running);
        }
    }

    private Task<BdResult> Answer(string commandLine)
    {
        if (held.TryGetValue(commandLine, out var holding))
        {
            return holding.Task;
        }

        if (changes.TryGetValue(commandLine, out var change))
        {
            change();
        }

        return Task.FromResult(
            scripted.TryGetValue(commandLine, out var answer)
                ? answer
                : new BdResult(1, string.Empty, $"unscripted run: {commandLine}"));
    }

    private static void InterlockedMax(ref int most, int candidate)
    {
        var seen = Volatile.Read(ref most);
        while (candidate > seen)
        {
            var before = Interlocked.CompareExchange(ref most, candidate, seen);
            if (before == seen)
            {
                return;
            }

            seen = before;
        }
    }
}
