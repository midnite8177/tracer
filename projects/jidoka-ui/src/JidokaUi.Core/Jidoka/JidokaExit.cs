namespace JidokaUi.Core.Jidoka;

/// <summary>
/// The exit codes of jidoka's gate and rules scripts, as the scripts document them. A script that
/// refuses a request writes nothing and exits with 1, and the gate script has three more codes for a
/// merge that stopped on the way.
/// </summary>
public static class JidokaExit
{
    /// <summary>The script refused the request, or failed before it changed anything, and wrote nothing.</summary>
    public const int Refused = 1;

    /// <summary>The script took arguments it does not know, and wrote nothing.</summary>
    public const int UsageError = 2;

    /// <summary>A merge waits on uncommitted edits in main's checkout, and main is unchanged.</summary>
    public const int WaitingOnEdits = 3;

    /// <summary>A merge put the commit on main, but a closing step failed.</summary>
    public const int PartlyLanded = 4;

    /// <summary>A merge found the full suite red on the rebuilt commit, so the epic is back at the gate.</summary>
    public const int BackAtTheGate = 5;

    /// <summary>
    /// True when a script that exited with this code may have changed a bead, so the app must read the
    /// project again. A script that refused, took a bad argument or waits on edits changed none.
    /// </summary>
    public static bool MayHaveWritten(int exitCode) => exitCode is not (Refused or UsageError or WaitingOnEdits);
}
