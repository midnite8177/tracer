using System.Text.Json;

namespace TracerUi.Core.Beads;

/// <summary>Reads the JSON that bd prints. The shape of that JSON differs between versions.</summary>
public static class BdJson
{
    // The key under which a version of bd wraps its beads in one object.
    private const string WrapperName = "issues";

    /// <summary>Reads the beads out of the output. Gives false when the output is not JSON at all.</summary>
    public static bool TryParse(string output, out IReadOnlyList<BeadRecord> records)
    {
        var text = output.Trim();
        if (text.Length == 0)
        {
            records = [];
            return true;
        }

        var parsed = ParseOneDocument(text) ?? ParseOnePerLine(text);
        records = parsed ?? [];
        return parsed is not null;
    }

    // Gives null when the text is not one JSON document, for example when it is JSON lines.
    private static IReadOnlyList<BeadRecord>? ParseOneDocument(string text)
    {
        try
        {
            using var document = JsonDocument.Parse(text);
            return RecordsIn(document.RootElement);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    // Some versions of bd print one JSON object per line instead of one array.
    // Gives null when no line of the text is a JSON document.
    private static IReadOnlyList<BeadRecord>? ParseOnePerLine(string text)
    {
        var records = new List<BeadRecord>();
        var anyLineParsed = false;
        foreach (var line in text.Split('\n'))
        {
            var parsed = ParseOneDocument(line.Trim());
            if (parsed is not null)
            {
                records.AddRange(parsed);
                anyLineParsed = true;
            }
        }

        return anyLineParsed ? records : null;
    }

    private static IReadOnlyList<BeadRecord> RecordsIn(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Array)
        {
            return [.. element.EnumerateArray().Where(IsObject).Select(BeadRecord.Of)];
        }

        if (element.ValueKind != JsonValueKind.Object)
        {
            return [];
        }

        if (element.TryGetProperty(WrapperName, out var wrapped) && wrapped.ValueKind == JsonValueKind.Array)
        {
            return RecordsIn(wrapped);
        }

        return [BeadRecord.Of(element)];
    }

    private static bool IsObject(JsonElement element) => element.ValueKind == JsonValueKind.Object;
}
