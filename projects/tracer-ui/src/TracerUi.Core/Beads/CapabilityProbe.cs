using System.Text.RegularExpressions;

namespace TracerUi.Core.Beads;

/// <summary>Asks one installation of bd what it can do, and builds the capability map from the answers.</summary>
public static partial class CapabilityProbe
{
    public static BdCapabilities From(
        BdResult version,
        BdResult help,
        IReadOnlyDictionary<string, BdResult> commandHelp,
        IReadOnlyList<BeadRecord> sample,
        BdComments comments)
    {
        if (!version.Succeeded)
        {
            return BdCapabilities.Unknown(BdFailure.Describe(["version"], version));
        }

        var number = VersionIn(version.StandardOutput);
        var fields = BeadFields.ResolveFrom(sample);
        if (!help.Succeeded)
        {
            return BdCapabilities.WithoutVerbs(number, fields, comments, BdFailure.Describe(["--help"], help));
        }

        return new BdCapabilities(
            number,
            true,
            HelpText.VerbsIn(help.StandardOutput),
            SubcommandsOf(commandHelp),
            FlagsOf(commandHelp),
            fields,
            comments,
            string.Empty);
    }

    // The subcommands that each command offers. A command that holds its work in subcommands lists
    // them in its own help, in the same shape that bd lists its commands.
    private static IReadOnlyDictionary<string, IReadOnlyList<string>> SubcommandsOf(
        IReadOnlyDictionary<string, BdResult> commandHelp)
    {
        var subcommands = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        foreach (var (command, result) in commandHelp.Where(entry => entry.Value.Succeeded))
        {
            subcommands[command] = HelpText.VerbsIn(result.StandardOutput);
        }

        return subcommands;
    }

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> FlagsOf(
        IReadOnlyDictionary<string, BdResult> commandHelp)
    {
        var flags = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        foreach (var (command, result) in commandHelp.Where(entry => entry.Value.Succeeded))
        {
            flags[command] = HelpText.FlagsIn(result.StandardOutput);
        }

        return flags;
    }

    private static string VersionIn(string versionLine)
    {
        var line = versionLine.Trim();
        var number = VersionNumber().Match(line);
        return number.Success ? number.Value : line;
    }

    [GeneratedRegex(@"\d+(\.\d+)+")]
    private static partial Regex VersionNumber();
}
