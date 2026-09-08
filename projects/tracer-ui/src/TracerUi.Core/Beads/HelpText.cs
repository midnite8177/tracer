using System.Text.RegularExpressions;

namespace TracerUi.Core.Beads;

/// <summary>Reads the help that bd prints, because the help is the list of what this version can do.</summary>
public static partial class HelpText
{
    /// <summary>The command lines of the help are indented, and they start with the name of the verb.</summary>
    public static IReadOnlyList<string> VerbsIn(string help)
    {
        var verbs = new List<string>();
        foreach (var line in help.Split('\n'))
        {
            var match = CommandLine().Match(line);
            if (match.Success)
            {
                verbs.Add(match.Groups["verb"].Value);
            }
        }

        return verbs;
    }

    [GeneratedRegex(@"^\s{2,4}(?<verb>[a-z][a-z-]*)\s{2,}\S")]
    private static partial Regex CommandLine();

    /// <summary>
    /// The long flags that the help declares, each with its two dashes. A flag declaration starts its
    /// own line, after an indent and an optional short form, so prose that names a flag does not count.
    /// </summary>
    public static IReadOnlyList<string> FlagsIn(string help)
    {
        var flags = new List<string>();
        foreach (var line in help.Split('\n'))
        {
            var match = FlagDeclaration().Match(line);
            if (match.Success)
            {
                flags.Add(match.Groups["flag"].Value);
            }
        }

        return [.. flags.Distinct()];
    }

    [GeneratedRegex(@"^\s{2,}(-[A-Za-z], )?(?<flag>--[a-z][a-z0-9-]*)")]
    private static partial Regex FlagDeclaration();
}
