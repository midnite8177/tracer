namespace TracerUi.Core.Beads;

/// <summary>Turns a failed run of bd into a message that a person can read.</summary>
public static class BdFailure
{
    public static string Describe(IReadOnlyList<string> arguments, BdResult result)
    {
        var command = $"bd {string.Join(' ', arguments)}";
        var reason = result.StandardError.Trim();
        return reason.Length > 0
            ? $"{command} failed: {reason}"
            : $"{command} failed with exit code {result.ExitCode}.";
    }
}
