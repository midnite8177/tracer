using System.Text.Json;
using JidokaUi.Core.Jidoka;

namespace JidokaUi.Core.Projects;

/// <summary>
/// Reads the onboarded repos from the repo settings that jidoka keeps in its home, one file for each
/// repo under <c>repos/</c>. The app only reads them: jidoka alone writes or removes a settings file.
/// </summary>
/// <remarks>
/// A settings file that is not JSON, or that names no absolute main worktree, is skipped, because
/// one broken file must not hide the other repos. The name of a file carries no meaning here, only
/// its <c>main_worktree</c> key does.
/// </remarks>
public sealed class OnboardedProjectFiles : IOnboardedProjects
{
    private const string MainWorktreeKey = "main_worktree";

    private readonly string settingsFolder;

    public OnboardedProjectFiles(JidokaHome jidokaHome)
    {
        settingsFolder = jidokaHome.ReposFolder;
    }

    public IReadOnlyList<ProjectPath> Paths()
    {
        if (!Directory.Exists(settingsFolder))
        {
            return [];
        }

        return
        [
            .. Directory.EnumerateFiles(settingsFolder, "*.json")
                .Order(StringComparer.Ordinal)
                .Select(MainWorktreeOf)
                .OfType<ProjectPath>()
                .Distinct(),
        ];
    }

    private static ProjectPath? MainWorktreeOf(string settingsFile)
    {
        try
        {
            using var stream = File.OpenRead(settingsFile);
            using var document = JsonDocument.Parse(stream);
            var root = document.RootElement;
            if (root.ValueKind == JsonValueKind.Object
                && root.TryGetProperty(MainWorktreeKey, out var value)
                && value.ValueKind == JsonValueKind.String
                && value.GetString() is { } text
                && ProjectPath.TryFromAbsolute(text, out var path))
            {
                return path;
            }

            return null;
        }
        catch (Exception exception) when (exception is JsonException or IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }
}
