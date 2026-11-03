namespace JidokaUi.Core.Boards;

/// <summary>One answer that a question offers, and how sure the worker was that it is the right one.</summary>
/// <param name="Name">The words of the answer, which the answer comment carries as they are.</param>
/// <param name="Confidence">The worker's confidence, in whole percent from 0 to 100, or null when the option carries none.</param>
/// <param name="Next">What happens next if the human picks this option, or null when the option does not say.</param>
public sealed record QuestionOption(string Name, int? Confidence, string? Next);

/// <summary>The call that the lap mod denied a worker, which a permission question asks the human to allow.</summary>
/// <param name="Call">The command as the worker ran it.</param>
/// <param name="Reason">The worker's reason for running the command, or null when it gave none.</param>
public sealed record DeniedCall(string Call, string? Reason);

/// <summary>
/// The question that jidoka asked on a bead, with the options it offers and the name of the one it
/// recommends. jidoka keeps all of it in the metadata of the bead, so the question needs no page.
/// </summary>
/// <param name="Sentence">The question in one sentence, or null when the bead does not keep one.</param>
/// <param name="Options">The options in the order that jidoka wrote them, never fewer than one.</param>
/// <param name="Recommended">The name of the recommended option, or an empty string when none matches.</param>
/// <param name="Denied">The call that a permission question asks about, or null when the question is no permission question.</param>
public sealed record BeadQuestion(string? Sentence, IReadOnlyList<QuestionOption> Options, string Recommended, DeniedCall? Denied)
{
    /// <summary>True when this option is the one that the worker recommends.</summary>
    public bool Recommends(QuestionOption option) =>
        Recommended.Length > 0 && string.Equals(option.Name, Recommended, StringComparison.Ordinal);
}
