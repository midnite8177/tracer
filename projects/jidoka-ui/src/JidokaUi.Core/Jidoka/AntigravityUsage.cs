using System.Globalization;
using System.Text.Json;

namespace JidokaUi.Core.Jidoka;

/// <summary>
/// One usage window of a bucket: how much of it is used, and the moment it resets when jidoka's file
/// names one.
/// </summary>
/// <param name="UsedPercent">The share of the window that is used.</param>
/// <param name="ResetsAt">The moment the window resets, or null when the reading names none.</param>
public sealed record UsageWindow(double UsedPercent, DateTimeOffset? ResetsAt)
{
    /// <summary>The window as a person reads it: the use, and the time left to its reset.</summary>
    public string Words(DateTimeOffset now)
    {
        var used = $"{UsedPercent.ToString("G6", CultureInfo.InvariantCulture)}% used";
        if (ResetsAt is not { } resets)
        {
            return used;
        }

        return resets > now ? $"{used}, resets in {Span(resets - now)}" : $"{used}, has reset";
    }

    /// <summary>A span in words: seconds, minutes, or hours and minutes, such as 45s, 12m or 3h05m.</summary>
    public static string Span(TimeSpan span)
    {
        var seconds = (long)span.TotalSeconds;
        return seconds switch
        {
            < 60 => $"{seconds}s",
            < 3600 => $"{seconds / 60}m",
            _ => $"{seconds / 3600}h{seconds % 3600 / 60:00}m",
        };
    }
}

/// <summary>
/// The part of the Antigravity account's quota that one family of models draws on. A bucket that has
/// only one of its two windows holds null for the other, which a person reads as none.
/// </summary>
/// <param name="Name">The bucket, such as the family of Gemini models it serves.</param>
/// <param name="Session">The five-hour window.</param>
/// <param name="Weekly">The weekly window.</param>
public sealed record UsageBucket(string Name, UsageWindow? Session, UsageWindow? Weekly);

/// <summary>The Antigravity account's quota as T3 last gave it, by bucket.</summary>
/// <param name="CheckedAt">The moment T3 last read the quota from Google.</param>
/// <param name="Buckets">The buckets, in the order the file holds them.</param>
public sealed record AntigravityReading(DateTimeOffset CheckedAt, IReadOnlyList<UsageBucket> Buckets);

/// <summary>
/// The file that jidoka's scheduler writes with the Antigravity account's quota, which the app reads
/// and never writes. A missing file, one that cannot be read or has another shape, and a reading
/// that T3 checked more than ten minutes ago all count as no reading, never as a use of zero.
/// </summary>
public sealed class AntigravityUsage
{
    /// <summary>How old a reading may be and still count, as jidoka's scheduler counts it.</summary>
    public static readonly TimeSpan FreshLimit = TimeSpan.FromMinutes(10);

    private readonly JidokaHome home;

    public AntigravityUsage(JidokaHome home)
    {
        this.home = home;
    }

    /// <summary>The reading that the file holds, or null when there is no fresh, well-formed one.</summary>
    public AntigravityReading? ReadingAt(DateTimeOffset now)
    {
        try
        {
            using var file = JsonDocument.Parse(File.ReadAllText(home.AntigravityUsageFile));
            var root = file.RootElement;
            if (root.ValueKind != JsonValueKind.Object
                || !WholeSeconds(root, "checkedAt", out var checkedSeconds)
                || !root.TryGetProperty("buckets", out var buckets)
                || buckets.ValueKind != JsonValueKind.Object)
            {
                return null;
            }

            var checkedAt = DateTimeOffset.FromUnixTimeSeconds(checkedSeconds);
            if (now - checkedAt > FreshLimit)
            {
                return null;
            }

            var held = buckets.EnumerateObject()
                .Where(bucket => bucket.Value.ValueKind == JsonValueKind.Object)
                .Select(bucket => new UsageBucket(
                    bucket.Name,
                    WindowIn(bucket.Value, "session"),
                    WindowIn(bucket.Value, "weekly")));
            return new AntigravityReading(checkedAt, [.. held]);
        }
        catch (Exception unreadable) when (unreadable is
            IOException or UnauthorizedAccessException or JsonException or ArgumentOutOfRangeException)
        {
            return null;
        }
    }

    private static UsageWindow? WindowIn(JsonElement bucket, string kind)
    {
        if (!bucket.TryGetProperty(kind, out var window)
            || window.ValueKind != JsonValueKind.Object
            || !window.TryGetProperty("usedPercent", out var used)
            || used.ValueKind != JsonValueKind.Number)
        {
            return null;
        }

        DateTimeOffset? resetsAt = WholeSeconds(window, "resetsAt", out var seconds)
            ? DateTimeOffset.FromUnixTimeSeconds(seconds)
            : null;
        return new UsageWindow(used.GetDouble(), resetsAt);
    }

    private static bool WholeSeconds(JsonElement root, string name, out long value)
    {
        value = 0;
        return root.TryGetProperty(name, out var found)
            && found.ValueKind == JsonValueKind.Number
            && found.TryGetInt64(out value);
    }
}
