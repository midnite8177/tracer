using System.Text.Json;

namespace TracerUi.Core.Beads;

/// <summary>One bead as bd printed it, before the app maps the field names.</summary>
public sealed class BeadRecord
{
    private readonly IReadOnlyDictionary<string, JsonElement> fields;

    public BeadRecord(IReadOnlyDictionary<string, JsonElement> fields)
    {
        this.fields = fields;
    }

    /// <summary>The JSON field names that this version of bd emitted, in no order a caller may rely on.</summary>
    public IReadOnlyList<string> FieldNames => [.. fields.Keys];

    /// <summary>The number in one field, or <paramref name="whenAbsent"/> when no such field holds a number.</summary>
    public long Number(IReadOnlyList<string> candidateNames, long whenAbsent) =>
        TryFirst(candidateNames, JsonValueKind.Number, out var value) && value.TryGetInt64(out var number)
            ? number
            : whenAbsent;

    /// <summary>
    /// The texts in one array field, or an empty list when this bead has no such field. bd writes an
    /// array of strings in some versions and an array of objects in others, so an object gives up its
    /// name, its id or its title.
    /// </summary>
    public IReadOnlyList<string> Strings(IReadOnlyList<string> candidateNames) =>
        TryFirst(candidateNames, JsonValueKind.Array, out var value)
            ? [.. value.EnumerateArray().Select(TextOf).Where(text => text.Length > 0)]
            : [];

    /// <summary>
    /// The dependency edges in one array field, or an empty list when this bead has no such field.
    /// </summary>
    public IReadOnlyList<BeadEdge> Edges(IReadOnlyList<string> candidateNames) =>
        TryFirst(candidateNames, JsonValueKind.Array, out var value)
            ? [.. value.EnumerateArray().Where(IsObject).Select(Of).Select(EdgeOf)]
            : [];

    private static bool IsObject(JsonElement element) => element.ValueKind == JsonValueKind.Object;

    // One edge is a record of its own, so it reads its two fields through the same walk of the
    // candidate names that every other field of a bead uses.
    private static BeadEdge EdgeOf(BeadRecord edge) =>
        new(edge.Text(BeadFields.TypeOfAnEdge), edge.Text(BeadFields.TargetOfAnEdge));

    /// <summary>The fields of one JSON object, as this record reads them.</summary>
    public static BeadRecord Of(JsonElement element)
    {
        var fields = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        foreach (var property in element.EnumerateObject())
        {
            fields[property.Name] = property.Value.Clone();
        }

        return new BeadRecord(fields);
    }

    private static string TextOf(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.String)
        {
            return element.GetString() ?? string.Empty;
        }

        if (element.ValueKind != JsonValueKind.Object)
        {
            return string.Empty;
        }

        foreach (var name in (string[])["name", "id", "title"])
        {
            if (element.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String)
            {
                return value.GetString() ?? string.Empty;
            }
        }

        return string.Empty;
    }

    /// <summary>The text of one field, or an empty string when this bead has no such field.</summary>
    public string Text(IReadOnlyList<string> candidateNames) =>
        TryFirst(candidateNames, JsonValueKind.String, out var value)
            ? value.GetString() ?? string.Empty
            : string.Empty;

    // The value of the first candidate name that this bead sets to a value of the wanted kind.
    // Every reader shares this walk, because a version of bd gives one field several names.
    private bool TryFirst(IReadOnlyList<string> candidateNames, JsonValueKind kind, out JsonElement found)
    {
        foreach (var name in candidateNames)
        {
            if (fields.TryGetValue(name, out var value) && value.ValueKind == kind)
            {
                found = value;
                return true;
            }
        }

        found = default;
        return false;
    }
}
