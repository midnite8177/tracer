using Microsoft.AspNetCore.Components;
using JidokaUi.Core.Beads;
using JidokaUi.Core.Jidoka;

namespace JidokaUi.Web.Components.Pages;

/// <summary>
/// A component that runs jidoka's scripts for one epic: the gate box, the gate items box and the
/// rules box. It holds what every such box shows about a run, whether one is going, how it ended and
/// what the person reads, and it holds the rule that a box reads its script once for each epic and
/// drops an answer that comes back for an epic it has left. It is the counterpart of
/// <see cref="CapabilityAware"/> for writes that go through a script and not through bd.
/// </summary>
public abstract class JidokaWriteAware : ComponentBase
{
    private BeadAddress? theEpicRead;

    [Inject]
    public required JidokaAdapter Jidoka { get; set; }

    /// <summary>Null until a run of this component reported; then what the person reads about it.</summary>
    protected string? WriteMessage { get; private set; }

    /// <summary>True when the last run succeeded, so the message reads as good news.</summary>
    protected bool Wrote { get; private set; }

    /// <summary>True from the moment a press starts a run until the script answers.</summary>
    protected bool Writing { get; private set; }

    /// <summary>
    /// <see cref="Writing"/>, in the words that aria-busy takes. Blazor renders a bool attribute by
    /// presence, but aria-busy is a string state, so a control writes this instead of the flag.
    /// </summary>
    protected string AriaBusy => Writing ? "true" : "false";

    /// <summary>
    /// Runs one script of jidoka and reports it. A second press while one run goes does nothing.
    /// </summary>
    /// <param name="run">Starts the script.</param>
    /// <param name="whenWritten">What the person reads when the script wrote, from what it printed.</param>
    /// <returns>The outcome, or null when a run was already going and this press started none.</returns>
    protected async Task<JidokaWriteOutcome?> WriteAsync(
        Func<Task<JidokaWriteOutcome>> run, Func<JidokaWriteOutcome, string> whenWritten)
    {
        if (Writing)
        {
            return null;
        }

        Writing = true;
        StateHasChanged();
        JidokaWriteOutcome outcome;
        try
        {
            outcome = await run();
        }
        finally
        {
            Writing = false;
            StateHasChanged();
        }

        Wrote = outcome.Wrote;
        WriteMessage = outcome.Wrote ? whenWritten(outcome) : outcome.Message;
        return outcome;
    }

    /// <summary>
    /// True the first time this epic comes, and false for every later call with the same epic, so a
    /// box reads its script once for each epic it shows.
    /// </summary>
    protected bool StartsReading(BeadAddress epic)
    {
        if (epic.Equals(theEpicRead))
        {
            return false;
        }

        theEpicRead = epic;
        return true;
    }

    /// <summary>
    /// True while the box still shows the epic that a read was asked for, so an answer for an epic the
    /// box has left is dropped.
    /// </summary>
    protected bool IsStillReading(BeadAddress asked) => asked.Equals(theEpicRead);
}
