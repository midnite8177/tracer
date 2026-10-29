namespace JidokaUi.Core.Boards;

/// <summary>One answer that a question offers, and how sure the worker was that it is the right one.</summary>
/// <param name="Name">The words of the answer, which the answer comment carries as they are.</param>
/// <param name="Confidence">The worker's confidence, in whole percent from 0 to 100.</param>
public sealed record QuestionOption(string Name, int Confidence);

/// <summary>
/// The question that jidoka asked on a bead, with the options it offers and the name of the one it
/// recommends. jidoka keeps both in the metadata of the bead, so the question needs no page.
/// </summary>
/// <param name="Options">The options in the order that jidoka wrote them, never fewer than one.</param>
/// <param name="Recommended">The name of the recommended option, or an empty string when none matches.</param>
public sealed record BeadQuestion(IReadOnlyList<QuestionOption> Options, string Recommended)
{
    /// <summary>True when this option is the one that the worker recommends.</summary>
    public bool Recommends(QuestionOption option) =>
        Recommended.Length > 0 && string.Equals(option.Name, Recommended, StringComparison.Ordinal);
}
