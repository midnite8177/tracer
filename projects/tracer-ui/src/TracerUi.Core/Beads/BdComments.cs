namespace TracerUi.Core.Beads;

/// <summary>
/// What the probe learned about the comments of a bead. bd holds them behind their own command,
/// so the probe reads the comments of one bead to learn the names.
/// </summary>
/// <param name="Fields">The JSON name that this bd emits for each comment field the UI reads.</param>
/// <param name="Problem">Empty when the probe read the comments; otherwise the reason it read none.</param>
public sealed record BdComments(IReadOnlyDictionary<string, string> Fields, string Problem)
{
    /// <summary>True when bd printed the comments of a bead, so the field map means something.</summary>
    public bool Answered => Problem.Length == 0;

    /// <summary>The probe read no comment, so it learned no name.</summary>
    public static BdComments Unread(string problem) =>
        new(BeadFields.ResolveCommentsFrom([]), problem);
}
