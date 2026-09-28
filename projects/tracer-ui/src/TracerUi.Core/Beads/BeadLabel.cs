using System.Diagnostics.CodeAnalysis;

namespace TracerUi.Core.Beads;

/// <summary>
/// One label as a write states it. bd takes any word as a label, so this type buys no more than the
/// shape a label needs: a word with no blank run around it, because a blank label reads as none.
/// </summary>
public sealed record BeadLabel
{
    private BeadLabel(string word)
    {
        Word = word;
    }

    /// <summary>What a person reads when a label gets a blank word.</summary>
    public const string NeedsAWord = "A label needs a word.";

    /// <summary>What a person reads when a typed label holds a comma.</summary>
    public const string HoldsNoComma = "A label cannot hold a comma, because bd reads it as two labels.";

    public string Word { get; }

    public static bool TryFrom(string text, [NotNullWhen(true)] out BeadLabel? label)
    {
        var trimmed = text.Trim();
        label = trimmed.Length > 0 ? new BeadLabel(trimmed) : null;
        return label is not null;
    }

    /// <summary>
    /// Reads a word that a person typed for a label flag. It refuses a word that
    /// <see cref="BdAdapter.ChangeLabelsAsync"/> cannot send as one label, and says why.
    /// </summary>
    public static bool TryFromTyped(
        string typed,
        [NotNullWhen(true)] out BeadLabel? label,
        [NotNullWhen(false)] out string? whyNot)
    {
        if (typed.Contains(',', StringComparison.Ordinal))
        {
            label = null;
            whyNot = HoldsNoComma;
            return false;
        }

        if (!TryFrom(typed, out label))
        {
            whyNot = NeedsAWord;
            return false;
        }

        whyNot = null;
        return true;
    }

    /// <summary>
    /// True when the word spells this label in any case. The app treats the two as one label, so that
    /// a project keeps one spelling of each.
    /// </summary>
    public bool ReadsTheSameAs(string word) => string.Equals(Word, word, StringComparison.OrdinalIgnoreCase);

    public override string ToString() => Word;
}
