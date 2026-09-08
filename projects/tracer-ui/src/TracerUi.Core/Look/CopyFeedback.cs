namespace TracerUi.Core.Look;

/// <summary>
/// The machine text that a person pressed the copy button for last, and what the browser did with
/// it. One browser session holds one of these, thus a page of many buttons marks one text at a
/// time. A page that opens has no mark, because no press has happened yet.
/// </summary>
public sealed class CopyFeedback
{
    private MarkedText? marked;

    /// <summary>
    /// Runs when the mark moves. Each copy button listens, because a press moves the mark off
    /// another button that the same press does not draw.
    /// </summary>
    public event Action? Changed;

    /// <summary>
    /// What the copy button beside this text must say about the last press. At most one text
    /// carries the mark, so every other text stays silent.
    /// </summary>
    public CopyOutcome Outcome(string text) =>
        marked is { } mark && string.Equals(text, mark.Text, StringComparison.Ordinal)
            ? mark.Outcome
            : CopyOutcome.None;

    /// <summary>
    /// Records that the clipboard now holds this text. One text carries the mark at a time, so a
    /// press for another text moves it.
    /// </summary>
    public void Took(string text) => Mark(text, CopyOutcome.Took);

    /// <summary>Records that the page reaches no clipboard, so the press for this text found none.</summary>
    public void FoundNoClipboard(string text) => Mark(text, CopyOutcome.NoClipboard);

    /// <summary>Records that the browser would not write this text to the clipboard that it has.</summary>
    public void Refused(string text) => Mark(text, CopyOutcome.Refused);

    /// <summary>
    /// What the copy button beside this text says, which a screen reader reads and a pointer shows.
    /// It names the text, because a page holds many of these buttons.
    /// </summary>
    public string Says(string text) => Outcome(text) switch
    {
        CopyOutcome.Took => $"Copied {text}",
        CopyOutcome.NoClipboard or CopyOutcome.Refused => $"Cannot copy {text}. {Reason(text)}",
        _ => $"Copy {text}",
    };

    /// <summary>
    /// Why the clipboard beside this text holds nothing, in the words that the button shows on the
    /// screen. It names no text, because the text stands beside the words. A press that reached a
    /// clipboard has no reason at all, and that press gives null.
    /// </summary>
    public string? Reason(string text) => Outcome(text) switch
    {
        CopyOutcome.NoClipboard => "The browser needs a secure connection.",
        CopyOutcome.Refused => "The browser would not write to the clipboard.",
        _ => null,
    };

    private void Mark(string text, CopyOutcome what)
    {
        marked = new MarkedText(text, what);
        Changed?.Invoke();
    }

    private sealed record MarkedText(string Text, CopyOutcome Outcome);
}
