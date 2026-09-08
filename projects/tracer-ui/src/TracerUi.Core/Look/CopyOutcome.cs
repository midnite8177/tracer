namespace TracerUi.Core.Look;

/// <summary>
/// What the browser did with the text that a person pressed the copy button for. The clipboard of a
/// browser has more than one way to say no, and the copy button says a different thing for each.
/// </summary>
public enum CopyOutcome
{
    /// <summary>No press of a copy button carries this text.</summary>
    None,

    /// <summary>The clipboard holds the text.</summary>
    Took,

    /// <summary>
    /// The page reaches no clipboard at all, because it carries no secure context. This is the
    /// state of every page that LAN mode serves.
    /// </summary>
    NoClipboard,

    /// <summary>The page reaches a clipboard, but the browser would not write the text to it.</summary>
    Refused,
}
