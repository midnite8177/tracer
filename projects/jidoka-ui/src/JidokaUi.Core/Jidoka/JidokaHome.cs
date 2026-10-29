namespace JidokaUi.Core.Jidoka;

/// <summary>
/// The folder that holds what jidoka keeps for a person: its settings, its ledger and its pages. The
/// environment can name another one, which is how jidoka's own scripts find it. This type names each
/// file and folder under the root, so a module that reads one of them asks here and does not know
/// the layout.
/// </summary>
/// <param name="Root">The folder itself.</param>
public sealed record JidokaHome(string Root)
{
    /// <summary>The environment variable that names the home.</summary>
    public const string EnvironmentVariable = "JIDOKA_HOME";

    /// <summary>The file that records the Python and the routes that jidoka's installer chose.</summary>
    public string SettingsFile => Path.Combine(Root, "settings.json");

    /// <summary>The folder that holds one snapshot of jidoka's scripts for each installed version.</summary>
    public string PluginsFolder => Path.Combine(Root, "plugins");

    /// <summary>The folder that holds the repo settings, one file for each onboarded repo.</summary>
    public string ReposFolder => Path.Combine(Root, "repos");

    /// <summary>The folder that holds the pages that jidoka's scripts write, a folder for each repo.</summary>
    public string PagesFolder => Path.Combine(Root, "pages");

    /// <summary>The folder that holds the heartbeat file of each epic that a manager runs.</summary>
    public string HeartbeatFolder => Path.Combine(Root, "heartbeat");

    /// <summary>The SQLite file that holds the runs of jidoka's workers.</summary>
    public string LedgerFile => Path.Combine(Root, "ledger.sqlite");

    /// <summary>The home that the environment names, or the folder under the user's profile.</summary>
    /// <param name="fromEnvironment">The value of <see cref="EnvironmentVariable"/>, or null when it is unset.</param>
    /// <param name="userProfile">The folder of the user's profile.</param>
    public static JidokaHome Locate(string? fromEnvironment, string userProfile) =>
        new(string.IsNullOrWhiteSpace(fromEnvironment) ? Path.Combine(userProfile, ".jidoka") : fromEnvironment);
}
