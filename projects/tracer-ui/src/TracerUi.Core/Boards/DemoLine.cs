using System.Text.RegularExpressions;

namespace TracerUi.Core.Boards;

/// <summary>The Demo line of a bead: what a person can do or see after the bead is closed.</summary>
public static partial class DemoLine
{
    /// <summary>The Demo line of this description, or an empty string when it has none.</summary>
    public static string In(string description)
    {
        var match = Section().Match(description);
        return match.Success
            ? string.Join(' ', match.Groups[1].Value.Split(OnAnyWhitespace, StringSplitOptions.RemoveEmptyEntries))
            : string.Empty;
    }

    // The separator that Split reads as "break on any run of whitespace". It is typed, because a
    // plain null at the callsite is ambiguous between this overload and the one that takes strings.
    private static readonly char[]? OnAnyWhitespace = null;

    [GeneratedRegex(@"^##\s*Demo\s*$\r?\n(.+?)(?:\r?\n\s*\r?\n|\r?\n##|\z)",
        RegexOptions.Singleline | RegexOptions.Multiline)]
    private static partial Regex Section();
}
