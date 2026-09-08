using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using TracerUi.Core.Beads;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// The box that a press to edit opens on the title or on the description of a bead. It owns what
/// the two share: the press that opens it, the field that takes the words, the key that closes it,
/// and where the keyboard stands after each of those. A child says what its own field holds and
/// what its write sends to bd.
/// </summary>
public abstract class ProseBox : CapabilityAware
{
    // Where the keyboard stands after the next render, which a press or a close moves.
    private enum WhatToFocus
    {
        Nothing,
        TheBox,
        TheField,
        ThePress,
    }

    private WhatToFocus focus = WhatToFocus.Nothing;

    /// <summary>The control that opens the box, which the keyboard returns to when it closes.</summary>
    protected ElementReference Press { get; set; }

    /// <summary>The open box, which takes the keyboard while it carries no field of its own.</summary>
    protected ElementReference Box { get; set; }

    /// <summary>The field that takes the words of the person.</summary>
    protected ElementReference Field { get; set; }

    /// <summary>True while the box stands open in the place of the words.</summary>
    protected bool Editing { get; private set; }

    /// <summary>The write that this box runs, which says whether the installed bd can take it.</summary>
    protected abstract UiVerb Verb { get; }

    /// <summary>
    /// Runs when a person closed this box and wrote nothing, so that whatever put the box on the
    /// page can take it off again.
    /// </summary>
    [Parameter]
    public EventCallback OnClosed { get; set; }

    /// <summary>
    /// What the open box says in place of the field: the refusal of a write that this bd cannot
    /// do, or a word that the probe has not answered yet. Empty while this bd takes the write.
    /// </summary>
    protected string Refusal =>
        Probed
            ? Why(Verb)
            : "The app is still asking bd what it can do.";

    /// <summary>Empty when the last write landed, or when none has run.</summary>
    protected string WhyTheLastWriteFailed => Wrote ? string.Empty : WriteMessage;

    /// <summary>
    /// Fills the field with what bd holds now. The page reads the bead again after every write, so
    /// the text that the person sees on open is never a stale copy of it.
    /// </summary>
    protected abstract void StartFromTheBead();

    /// <summary>Opens the box on the words that the bead carries.</summary>
    protected void Open()
    {
        StartFromTheBead();
        ForgetTheLastWrite();
        Editing = true;
        focus = Refusal.Length > 0 ? WhatToFocus.TheBox : WhatToFocus.TheField;
    }

    /// <summary>Closes the box and writes nothing.</summary>
    protected void Close()
    {
        Editing = false;
        ForgetTheLastWrite();
        focus = WhatToFocus.ThePress;
        _ = OnClosed.InvokeAsync();
    }

    protected void CloseOnEscape(KeyboardEventArgs key)
    {
        if (string.Equals(key.Key, "Escape", StringComparison.Ordinal))
        {
            Close();
        }
    }

    /// <summary>
    /// Runs one write of this box. A write that bd took closes the box, because the page reads the
    /// bead again and the words themselves then say what landed. A write that bd refused keeps the
    /// box open with what the person typed, so they correct it and try again.
    /// </summary>
    protected async Task SaveThen(Func<Task<BdWriteOutcome>> write, EventCallback onWritten)
    {
        if (await WriteAsync(write, onWritten))
        {
            Editing = false;
            focus = WhatToFocus.ThePress;
        }
    }

    // Moves the keyboard into the box that a press opened and back to the press when it closes, so
    // that a person who never touches a pointer keeps their place on the page.
    // firstRender goes unread: the press opens the box on a later render, not the first. There is
    // no base call because ComponentBase leaves this one empty.
    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        var what = focus;
        focus = WhatToFocus.Nothing;
        switch (what)
        {
            case WhatToFocus.TheBox:
                await Box.FocusAsync();
                break;
            case WhatToFocus.TheField:
                await Field.FocusAsync();
                break;
            case WhatToFocus.ThePress:
                await Press.FocusAsync();
                break;
        }
    }
}
