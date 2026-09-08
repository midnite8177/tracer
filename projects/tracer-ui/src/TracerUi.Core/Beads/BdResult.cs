namespace TracerUi.Core.Beads;

/// <summary>What one run of the bd command line gave back.</summary>
/// <param name="ExitCode">Zero when bd did the work; -1 when the app could not start bd at all.</param>
public sealed record BdResult(int ExitCode, string StandardOutput, string StandardError)
{
    public bool Succeeded => ExitCode == 0;
}
