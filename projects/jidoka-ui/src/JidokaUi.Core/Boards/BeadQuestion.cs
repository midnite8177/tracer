using System.Text.Json;

namespace JidokaUi.Core.Boards;

/// <summary>One answer that a question offers, and how sure the worker was that it is the right one.</summary>
/// <param name="Name">The words of the answer, which the answer comment carries as they are.</param>
/// <param name="Confidence">The worker's confidence, in whole percent from 0 to 100.</param>
public sealed record QuestionOption(string Name, int Confidence);

/// <summary>
/// The question that jidoka asked on a bead: the options it offers and the name of the one it
/// recommends. jidoka keeps both in the metadata of the bead, so the question needs no page.
/// </summary>
/// <param name="Options">The options in the order that jidoka wrote them, never fewer than one.</param>
/// <param name="Recommended">The name of the recommended option, or an empty string when none matches.</param>
public sealed record BeadQuestion(IReadOnlyList<QuestionOption> Options, string Recommended)
{
    private const string OptionsKey = "question.options";
    private const string RecommendedKey = "question.recommended";

    /// <summary>True when this option is the one that the worker recommends.</summary>
    public bool Recommends(QuestionOption option) =>
        Recommended.Length > 0 && string.Equals(option.Name, Recommended, StringComparison.Ordinal);

    /// <summary>
    /// The question that a bead carries in its metadata, or null when it carries none. Options that
    /// are not a JSON array of objects with a name make no question, because a panel cannot draw an
    /// answer it cannot name.
    /// </summary>
    public static BeadQuestion? From(IReadOnlyDictionary<string, string> metadata)
    {
        if (!metadata.TryGetValue(OptionsKey, out var written))
        {
            return null;
        }

        var options = OptionsIn(written);
        if (options.Count == 0)
        {
            return null;
        }

        return new BeadQuestion(options, metadata.GetValueOrDefault(RecommendedKey, string.Empty));
    }

    private static IReadOnlyList<QuestionOption> OptionsIn(string written)
    {
        try
        {
            using var document = JsonDocument.Parse(written);
            if (document.RootElement.ValueKind != JsonValueKind.Array)
            {
                return [];
            }

            return [.. document.RootElement.EnumerateArray().Select(OptionOf).OfType<QuestionOption>()];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    private static QuestionOption? OptionOf(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Object
            || !element.TryGetProperty("name", out var name)
            || name.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(name.GetString()))
        {
            return null;
        }

        var confidence = element.TryGetProperty("confidence", out var sure) && sure.TryGetInt32(out var percent)
            ? percent
            : 0;
        return new QuestionOption(name.GetString() ?? string.Empty, confidence);
    }
}
