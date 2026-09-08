namespace TracerUi.Core.Beads;

/// <summary>Runs the bd command line in one project directory.</summary>
public interface IBdProcess
{
    Task<BdResult> RunAsync(string workingDirectory, IReadOnlyList<string> arguments);
}
