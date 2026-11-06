namespace JidokaUi.Core.Beads;

/// <summary>Runs the bd command line in one project directory.</summary>
public interface IBdProcess
{
    /// <param name="stop">Kills the program and every process that it started, when cancelled.</param>
    Task<BdResult> RunAsync(string workingDirectory, IReadOnlyList<string> arguments, CancellationToken stop);
}
