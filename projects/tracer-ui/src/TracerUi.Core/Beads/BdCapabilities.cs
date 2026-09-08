namespace TracerUi.Core.Beads;

/// <summary>What the probe learned about the bd that this machine has installed.</summary>
/// <param name="Version">The version number, or the whole version line when it holds no number.</param>
/// <param name="VerbsKnown">True when the probe read the help of bd, so the verb map means something.</param>
/// <param name="Verbs">The commands that this bd offers.</param>
/// <param name="Subcommands">The subcommands of each command that the probe asked about.</param>
/// <param name="Flags">The flags of each command that the probe asked about.</param>
/// <param name="Fields">The JSON field name that this bd emits for each field the UI reads.</param>
/// <param name="Comments">What the probe learned about the comments of a bead.</param>
/// <param name="Problem">Empty when the probe ran; otherwise the reason it learned nothing.</param>
public sealed record BdCapabilities(
    string Version,
    bool VerbsKnown,
    IReadOnlyList<string> Verbs,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Subcommands,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Flags,
    IReadOnlyDictionary<string, string> Fields,
    BdComments Comments,
    string Problem)
{
    /// <summary>The probe learned nothing at all, because bd itself did not answer.</summary>
    public static BdCapabilities Unknown(string problem) =>
        WithoutVerbs(
            string.Empty,
            BeadFields.ResolveFrom([]),
            BdComments.Unread("The app could not run bd at all, so it read no comment."),
            problem);

    /// <summary>The probe reached bd but could not read its help, so the verb map stays unknown.</summary>
    public static BdCapabilities WithoutVerbs(
        string version,
        IReadOnlyDictionary<string, string> fields,
        BdComments comments,
        string problem) =>
        new(
            version,
            false,
            [],
            new Dictionary<string, IReadOnlyList<string>>(),
            new Dictionary<string, IReadOnlyList<string>>(),
            fields,
            comments,
            problem);

    public bool Supports(UiVerb verb) => MissingCapability(verb).Length == 0;

    /// <summary>Empty when the installed bd offers this action; otherwise what the installed bd lacks.</summary>
    public string MissingCapability(UiVerb verb)
    {
        if (!VerbsKnown)
        {
            return "The app could not ask this bd what it can do.";
        }

        if (!Verbs.Contains(verb.Command))
        {
            return $"bd has no {verb.Command} command.";
        }

        var subcommands = Subcommands.TryGetValue(verb.Command, out var offered) ? offered : [];
        var missingSubcommand = verb.Subcommands.FirstOrDefault(sub => !subcommands.Contains(sub));
        if (missingSubcommand is not null)
        {
            return $"bd {verb.Command} has no {missingSubcommand} subcommand.";
        }

        var flags = Flags.TryGetValue(verb.Command, out var known) ? known : [];
        var missing = verb.Flags.FirstOrDefault(flag => !flags.Contains(flag));
        return missing is null ? string.Empty : $"bd {verb.Command} has no {missing} flag.";
    }
}
