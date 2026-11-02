using JidokaUi.Core.Beads;

namespace JidokaUi.Core.Jidoka;

/// <summary>
/// Runs one program in one project directory, which is how the app starts jidoka's scripts. A run
/// gives the same result as a run of bd, an exit code and two streams, so the two share one type.
/// </summary>
public interface IJidokaProcess
{
    /// <param name="stop">Kills the program and every process that it started, when cancelled.</param>
    Task<BdResult> RunAsync(
        string program, string workingDirectory, IReadOnlyList<string> arguments, CancellationToken stop);
}
