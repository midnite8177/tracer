using System.Text.Json;

namespace JidokaUi.Core.Beads;

/// <summary>The one way that the app turns a JSON value into the text a person or a parser reads.</summary>
public static class JsonText
{
    /// <summary>
    /// The characters of a string value, or the JSON that any other value holds, so a reader that
    /// wants an array or a number out of it parses the text itself.
    /// </summary>
    public static string Of(JsonElement element) =>
        element.ValueKind == JsonValueKind.String ? element.GetString() ?? string.Empty : element.GetRawText();
}
