namespace JidokaUi.Core.Jidoka;

/// <summary>
/// A kind of jidoka page that the app serves beside a bead. Each kind is the word that the file name
/// of its page starts with.
/// </summary>
public enum JidokaPageKind
{
    /// <summary>The page beside a task that jidoka parked on a question.</summary>
    Question,

    /// <summary>The review guide beside an epic that waits at the acceptance gate.</summary>
    Gate,

    /// <summary>The page beside an epic that shows the task table of its handoff.</summary>
    Handoff,

    /// <summary>The page beside an epic that shows the acceptance specs proposed for it, each case beside its plain reading.</summary>
    SpecApproval,
}

/// <summary>The words that name the kinds of jidoka page, in file names and in addresses.</summary>
public static class JidokaPageKinds
{
    /// <summary>The word that the file name and the address of a page of this kind start with.</summary>
    public static string Word(this JidokaPageKind kind) => kind switch
    {
        JidokaPageKind.Question => "question",
        JidokaPageKind.Gate => "gate",
        JidokaPageKind.Handoff => "handoff",
        JidokaPageKind.SpecApproval => "spec-approval",
        _ => throw new ArgumentOutOfRangeException(nameof(kind), kind, "No script writes a page of this kind."),
    };

    /// <summary>Reads a word, such as one from an address. It gives false for a word that names no kind.</summary>
    public static bool TryFrom(string word, out JidokaPageKind kind)
    {
        foreach (var candidate in Enum.GetValues<JidokaPageKind>())
        {
            if (string.Equals(candidate.Word(), word, StringComparison.Ordinal))
            {
                kind = candidate;
                return true;
            }
        }

        kind = default;
        return false;
    }
}
