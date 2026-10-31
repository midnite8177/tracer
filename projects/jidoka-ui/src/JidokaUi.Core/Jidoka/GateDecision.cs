namespace JidokaUi.Core.Jidoka;

/// <summary>
/// One decision that the human writes on an epic at the acceptance gate: the mode of jidoka's gate
/// script and the arguments that follow the epic. A value of a flag joins its flag with an equals
/// sign, so a message or a reason that starts with a dash reaches the script as text.
/// </summary>
/// <param name="Mode">The word that picks the decision in the gate script.</param>
/// <param name="AfterTheEpic">The arguments that follow the epic id.</param>
/// <param name="TakesTheFullSuite">True when the script may run the full suite, which takes minutes and not seconds.</param>
public sealed record GateDecision(string Mode, IReadOnlyList<string> AfterTheEpic, bool TakesTheFullSuite)
{
    /// <summary>Lands the epic on local main as one commit, with this message, which names no bead.</summary>
    public static GateDecision Merge(string message) => new("merge", [$"--message={message}"], true);

    /// <summary>Closes the epic without landing it. Its epic branch stays.</summary>
    public static GateDecision Drop() => new("drop", [], false);

    /// <summary>Marks the numbered assumption of the gate comment wrong, for this reason.</summary>
    public static GateDecision Wrong(int number, string why) =>
        new("wrong", [number.ToString(System.Globalization.CultureInfo.InvariantCulture), $"--why={why}"], false);

    /// <summary>Promotes the numbered holdout, so that landing files a planning bead that holds its scenario.</summary>
    public static GateDecision Promote(int number) =>
        new("promote", [number.ToString(System.Globalization.CultureInfo.InvariantCulture)], false);

    /// <summary>Puts a test that the test cleanup removed back on the epic branch.</summary>
    public static GateDecision Restore(string test, string? file) =>
        new("restore", file is null ? [test] : [test, $"--file={file}"], false);

    /// <summary>Leaves a bead that the gate lists as found outside the epic open.</summary>
    public static GateDecision KeepFinding(string bead) => new("keep-finding", [bead], false);

    /// <summary>Closes a bead that the gate lists as found outside the epic.</summary>
    public static GateDecision CloseFinding(string bead) => new("close-finding", [bead], false);
}
