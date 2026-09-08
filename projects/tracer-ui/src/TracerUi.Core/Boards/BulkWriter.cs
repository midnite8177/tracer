using TracerUi.Core.Beads;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>One bead of a bulk action that bd refused, with what bd said about it.</summary>
public sealed record BulkFailure(string BeadId, string Title, string Message);

/// <summary>
/// What a bulk action did. bd takes one bead at a time, so a bulk action is many writes and some of
/// them can fail. The report names the beads that failed, so that the person retries those alone.
/// </summary>
/// <param name="Message">Empty when the action ran; otherwise why it ran no write at all.</param>
public sealed record BulkReport(int Written, IReadOnlyList<BulkFailure> Failures, string Message)
{
    public static BulkReport Refused(string message) => new(0, [], message);

    public bool Whole => Message.Length == 0 && Failures.Count == 0;

    /// <summary>The beads that failed, so that the board selects those and nothing else.</summary>
    public IReadOnlyList<string> FailedIds => [.. Failures.Select(failure => failure.BeadId)];

    /// <summary>What the person reads after the action: what bd wrote, and what it refused.</summary>
    public string Summary
    {
        get
        {
            if (Message.Length > 0)
            {
                return Message;
            }

            var wrote = Written == 1 ? "bd wrote 1 bead." : $"bd wrote {Written} beads.";
            return Failures.Count == 0 ? wrote : $"{wrote} {Failures.Count} failed.";
        }
    }
}

/// <summary>
/// Runs one bulk action, one bead at a time. A bead that bd refuses does not stop the beads after
/// it, because a person who selected 20 beads wants the 19 that work.
/// </summary>
public sealed class BulkWriter
{
    private readonly BdAdapter adapter;

    public BulkWriter(BdAdapter adapter)
    {
        this.adapter = adapter;
    }

    public Task<BulkReport> RunAsync(ProjectPath project, BulkPlan plan)
    {
        if (!plan.IsReady)
        {
            return Task.FromResult(BulkReport.Refused(plan.Problem));
        }

        return adapter.GatherTheWritesAsync(() => WriteEachBeadAsync(project, plan));
    }

    private async Task<BulkReport> WriteEachBeadAsync(ProjectPath project, BulkPlan plan)
    {
        var written = 0;
        var failures = new List<BulkFailure>();
        foreach (var step in plan.Steps)
        {
            var outcome = await WriteAsync(new BeadAddress(project, step.BeadId), plan.Action, step);
            if (outcome.Wrote)
            {
                written++;
            }
            else
            {
                failures.Add(new BulkFailure(step.BeadId, step.Title, outcome.Message));
            }
        }

        return new BulkReport(written, failures, string.Empty);
    }

    private Task<BdWriteOutcome> WriteAsync(BeadAddress bead, BulkAction action, BulkStep step) =>
        action.Shape.Apply(adapter, bead, action, step);
}
