using System.Text.Json;
using JidokaUi.Core.Boards;

namespace JidokaUi.Core.Jidoka;

/// <summary>
/// The Python and the folder of scripts that the app starts for jidoka, as jidoka's own installer
/// recorded them under its home: the interpreter in <c>settings.json</c>, and the scripts in the
/// newest snapshot under <c>plugins/</c>.
/// </summary>
/// <param name="Python">The program that runs a script.</param>
/// <param name="Scripts">The folder that holds the scripts.</param>
public sealed record JidokaInstall(string Python, string Scripts)
{
    /// <summary>The full path of one script in the scripts folder.</summary>
    public string PathOf(string script) => Path.Combine(Scripts, script);

    /// <summary>
    /// Finds the install under this home, or says in words what is missing, because a machine without
    /// jidoka can still browse the board.
    /// </summary>
    public static Read<JidokaInstall> Find(JidokaHome home)
    {
        var settings = home.SettingsFile;
        if (PythonOf(settings) is not { } python)
        {
            return new Read<JidokaInstall>.Unread(
                $"jidoka's settings at {settings} name no Python. Run jidoka's install.py to record one.");
        }

        var plugins = home.PluginsFolder;
        return NewestScriptsIn(plugins) is { } scripts
            ? new Read<JidokaInstall>.Given(new JidokaInstall(python, scripts))
            : new Read<JidokaInstall>.Unread(
                $"jidoka has no installed scripts under {plugins}. Run jidoka's install.py.");
    }

    private static string? PythonOf(string settings)
    {
        try
        {
            using var document = JsonDocument.Parse(File.ReadAllText(settings));
            if (document.RootElement.ValueKind != JsonValueKind.Object
                || !document.RootElement.TryGetProperty("python", out var python)
                || python.ValueKind != JsonValueKind.String)
            {
                return null;
            }

            return string.IsNullOrWhiteSpace(python.GetString()) ? null : python.GetString();
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException or JsonException)
        {
            return null;
        }
    }

    private static string? NewestScriptsIn(string plugins)
    {
        if (!Directory.Exists(plugins))
        {
            return null;
        }

        var snapshots = new List<(Version Version, string Scripts)>();
        foreach (var folder in Directory.EnumerateDirectories(plugins))
        {
            var scripts = Path.Combine(folder, "jidoka", "scripts");
            if (Version.TryParse(Path.GetFileName(folder), out var version) && Directory.Exists(scripts))
            {
                snapshots.Add((version, scripts));
            }
        }

        return snapshots.Count == 0 ? null : snapshots.MaxBy(snapshot => snapshot.Version).Scripts;
    }
}
