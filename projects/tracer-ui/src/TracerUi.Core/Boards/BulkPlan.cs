namespace TracerUi.Core.Boards;

/// <summary>
/// What one action does to one bead of the selection.
/// </summary>
/// <param name="Reason">
/// The reason that a close writes for this bead. It starts as the shared reason of the action, and
/// the person edits it before the commit. Every other verb leaves it empty.
/// </param>
public sealed record BulkStep(string BeadId, string Title, string Reason);

/// <summary>
/// What an action of the action bar will do, as the person reads it before it commits. The plan
/// names every bead that it touches, so nobody acts on a selection they did not mean.
/// </summary>
public sealed record BulkPlan(BulkAction Action, IReadOnlyList<BulkStep> Steps)
{
    public static BulkPlan For(BulkAction action, IReadOnlyList<Bead> beads) =>
        new(action, [.. beads.Select(bead => new BulkStep(bead.Id, bead.Title, ReasonOf(action)))]);

    private static string ReasonOf(BulkAction action) =>
        action.Verb == BulkVerb.CloseWithAReason ? action.Value : string.Empty;

    /// <summary>The sentence that the person reads before the action commits.</summary>
    public string Summary => Action.Shape.Sentence(this);

    /// <summary>How the summary counts the beads of this action.</summary>
    public string Beads => Steps.Count == 1 ? "1 bead" : $"{Steps.Count} beads";

    /// <summary>How the summary says the reasons of a close divide, including when none of them differ.</summary>
    public string OwnReasons
    {
        get
        {
            var edited = Steps.Count(step => step.Reason != Action.Value);
            return edited switch
            {
                0 => "They all take the same reason.",
                1 => "1 of them takes a reason of its own.",
                _ => $"{edited} of them take a reason of their own.",
            };
        }
    }

    /// <summary>The same plan, with a reason that belongs to this bead alone.</summary>
    public BulkPlan WithReasonFor(string beadId, string reason) =>
        this with
        {
            Steps = [.. Steps.Select(step => step.BeadId == beadId ? step with { Reason = reason } : step)],
        };

    /// <summary>
    /// Empty when the action is ready to commit; otherwise what the person must still give. A close
    /// with no reason would leave a hole in the history of a bead, so the plan states it here and the
    /// action bar keeps the commit out of reach.
    /// </summary>
    public string Problem
    {
        get
        {
            if (Steps.Count == 0)
            {
                return "Select a bead first.";
            }

            if (Action.Verb == BulkVerb.CloseWithAReason)
            {
                var without = Steps.FirstOrDefault(step => step.Reason.Trim().Length == 0);
                if (without is not null)
                {
                    return $"Bead {without.BeadId} has no close reason.";
                }
            }
            else if (Action.Shape.NeedsAValue && Action.Value.Trim().Length == 0)
            {
                return $"This action needs a value: {Action.Shape.Name.ToLowerInvariant()}.";
            }

            return string.Empty;
        }
    }

    public bool IsReady => Problem.Length == 0;
}
