using System.Text.Json;
using JidokaUi.Core.Jidoka;

namespace JidokaUi.Core.Notifications;

/// <summary>
/// The last beat of one epic's manager, as jidoka's heartbeat file holds it. The file carries the age
/// limit too, so the app asks the beat whether it is stale and holds no limit of its own.
/// </summary>
/// <param name="Age">How long ago the manager last beat.</param>
/// <param name="FreshLimit">How old a beat may be and still count as fresh, as jidoka wrote it.</param>
public sealed record Heartbeat(TimeSpan Age, TimeSpan FreshLimit)
{
    /// <summary>True when the beat is older than jidoka lets a fresh one be.</summary>
    public bool IsStale => Age > FreshLimit;
}

/// <summary>
/// jidoka's heartbeat files, which the app reads and never writes. The manager of each epic that
/// the factory runs keeps one fresh, so a heartbeat that stops getting younger shows a stopped
/// factory.
/// </summary>
public sealed class Heartbeats
{
    private readonly JidokaHome home;

    public Heartbeats(JidokaHome home)
    {
        this.home = home;
    }

    /// <summary>
    /// The heartbeat of this epic, or null when the epic has none or the file cannot be read or
    /// names no time and no fresh limit. An epic that was handed off with no manager has no
    /// heartbeat, and that is no stop.
    /// </summary>
    public Heartbeat? BeatOf(string epicId, DateTimeOffset now)
    {
        if (epicId.Length == 0 || epicId.AsSpan().IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
        {
            return null;
        }

        try
        {
            using var file = JsonDocument.Parse(File.ReadAllText(Path.Combine(home.HeartbeatFolder, $"{epicId}.json")));
            if (file.RootElement.ValueKind != JsonValueKind.Object
                || !WholeNumber(file.RootElement, "time", out var seconds)
                || !WholeNumber(file.RootElement, "fresh_seconds", out var fresh)
                || fresh <= 0)
            {
                return null;
            }

            return new Heartbeat(now - DateTimeOffset.FromUnixTimeSeconds(seconds), TimeSpan.FromSeconds(fresh));
        }
        catch (Exception unreadable) when (unreadable is IOException or UnauthorizedAccessException or JsonException or ArgumentOutOfRangeException)
        {
            return null;
        }
    }

    private static bool WholeNumber(JsonElement root, string name, out long value)
    {
        value = 0;
        return root.TryGetProperty(name, out var found)
            && found.ValueKind == JsonValueKind.Number
            && found.TryGetInt64(out value);
    }
}
