using System.Text.Json;
using JidokaUi.Core.Jidoka;

namespace JidokaUi.Core.Notifications;

/// <summary>
/// jidoka's heartbeat files, which the app reads and never writes. The manager of each epic that
/// the factory runs keeps one fresh, so a heartbeat that stops getting younger shows a stopped
/// factory.
/// </summary>
public sealed class Heartbeats
{
    /// <summary>
    /// How old a heartbeat may be and still count as fresh, in seconds. It is jidoka's own limit, a
    /// beat and a half.
    /// </summary>
    public const int FreshSeconds = 90;

    private readonly JidokaHome home;

    public Heartbeats(JidokaHome home)
    {
        this.home = home;
    }

    /// <summary>
    /// How old the heartbeat of this epic is, or null when the epic has none or the file cannot be
    /// read. An epic that was handed off with no manager has no heartbeat, and that is no stop.
    /// </summary>
    public TimeSpan? AgeOf(string epicId, DateTimeOffset now)
    {
        if (epicId.Length == 0 || epicId.AsSpan().IndexOfAny(Path.GetInvalidFileNameChars()) >= 0)
        {
            return null;
        }

        try
        {
            using var file = JsonDocument.Parse(File.ReadAllText(Path.Combine(home.HeartbeatFolder, $"{epicId}.json")));
            if (file.RootElement.ValueKind != JsonValueKind.Object
                || !file.RootElement.TryGetProperty("time", out var beat)
                || beat.ValueKind != JsonValueKind.Number
                || !beat.TryGetInt64(out var seconds))
            {
                return null;
            }

            return now - DateTimeOffset.FromUnixTimeSeconds(seconds);
        }
        catch (Exception unreadable) when (unreadable is IOException or UnauthorizedAccessException or JsonException or ArgumentOutOfRangeException)
        {
            return null;
        }
    }

    /// <summary>True when the heartbeat is older than jidoka lets a fresh one be.</summary>
    public static bool IsStale(TimeSpan age) => age > TimeSpan.FromSeconds(FreshSeconds);
}
