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

    public string Word { get; }

    public static bool TryFrom(string text, [NotNullWhen(true)] out BeadLabel? label)
    {
        var trimmed = text.Trim();
        label = trimmed.Length > 0 ? new BeadLabel(trimmed) : null;
        return label is not null;
    }

    public override string ToString() => Word;
}
