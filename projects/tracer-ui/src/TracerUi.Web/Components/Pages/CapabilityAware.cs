using Microsoft.AspNetCore.Components;
using TracerUi.Core.Beads;
using TracerUi.Core.Projects;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// A component that offers a verb of the installed bd. It probes that bd once and answers the three
/// questions every such component asks: whether to enable the control, what the tooltip says when it
/// is disabled, and how one write went. Every write surface asks them the same way, so they live
/// here.
/// </summary>
public abstract class CapabilityAware : ComponentBase
{
    [Inject]
    public required BdAdapter Bd { get; set; }

    private BdCapabilities? capabilities;

    /// <summary>The project whose bd this component asks. A page names it.</summary>
    protected abstract ProjectPath OfProject { get; }

    /// <summary>True once the probe answered, so a page can say that it is still asking.</summary>
    protected bool Probed => capabilities is not null;

    protected override async Task OnInitializedAsync() => capabilities = await Bd.CapabilitiesAsync(OfProject);

    protected bool Can(UiVerb verb) => capabilities?.Supports(verb) ?? false;

    /// <summary>Empty when this bd offers the verb; otherwise what this bd lacks.</summary>
    protected string Why(UiVerb verb) => capabilities?.MissingCapability(verb) ?? string.Empty;

    /// <summary>Null until a write of this component reported; then what the person reads about it.</summary>
    protected string? WriteMessage { get; private set; }

    /// <summary>True when the last write of this component succeeded, so the message reads as good news.</summary>
    protected bool Wrote { get; private set; }

    /// <summary>True from the moment a press of this component starts a write until bd answers it.</summary>
    protected bool Writing { get; private set; }

    /// <summary>
    /// True once the last write gave up on bd. A press of a fact verb still lands twice as it lands
    /// once, so most surfaces still take a press; a subclass that must not risk a second write, such
    /// as a comment box, reads this instead.
    /// </summary>
    protected bool Abandoned { get; private set; }

    /// <summary>
    /// <see cref="Writing"/>, in the words that aria-busy takes. Blazor renders a bool attribute by
    /// presence, but aria-busy is a string state, so a control writes this instead of the flag.
    /// </summary>
    protected string AriaBusy => Writing ? "true" : "false";

    /// <summary>
    /// What the person reads after a write that succeeded. A component whose write replaces
    /// something says so, because "bd made the change" understates it.
    /// </summary>
    protected virtual string WhenWritten => "bd made the change.";

    /// <summary>
    /// Drops the report of the last write and its abandoned lock, so that a new form opens with no
    /// stale message.
    /// </summary>
    protected void ForgetTheLastWrite()
    {
        WriteMessage = null;
        Abandoned = false;
    }

    /// <summary>
    /// Runs one create and reports it. A create takes more than one write, so a bead can exist and
    /// the message still say what went wrong after bd made it; the caller reads the bead again
    /// whenever the bead exists, because it is there either way.
    /// </summary>
    /// <returns>True when every write of the create ran, so the new bead is what the app meant.</returns>
    protected async Task<bool> CreateAsync(Func<Task<BdCreateOutcome>> create, EventCallback onCreated)
    {
        Writing = true;
        StateHasChanged();
        BdCreateOutcome outcome;
        try
        {
            outcome = await create();
        }
        finally
        {
            Writing = false;

            // Renders now, before the await below: onCreated can run a slow reload of its own, and
            // with no render here the control would stay visually busy through that whole reload.
            StateHasChanged();
        }

        Wrote = outcome.Whole;
        Abandoned = outcome.GaveUp;
        WriteMessage = outcome.Message.Length > 0 ? outcome.Message : $"bd made {outcome.Id}.";
        if (outcome.Created)
        {
            await onCreated.InvokeAsync();
        }

        return outcome.Whole;
    }

    /// <summary>
    /// Runs one write and reports it. A write that succeeded makes the page read the bead again, so
    /// what the person sees is what bd holds. A write that failed keeps what the person typed, so
    /// they can correct it and try again.
    /// </summary>
    protected async Task<bool> WriteAsync(Func<Task<BdWriteOutcome>> write, EventCallback onWritten)
    {
        Writing = true;
        StateHasChanged();
        BdWriteOutcome outcome;
        try
        {
            outcome = await write();
        }
        finally
        {
            Writing = false;

            // Renders now, before the await below: onWritten can run a slow reload of its own, and
            // with no render here the control would stay visually busy through that whole reload.
            StateHasChanged();
        }

        Wrote = outcome.Wrote;
        Abandoned = outcome.GaveUp;
        WriteMessage = outcome.Wrote ? WhenWritten : outcome.Message;
        if (outcome.Wrote)
        {
            await onWritten.InvokeAsync();
        }

        return outcome.Wrote;
    }
}
