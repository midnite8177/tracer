using TracerUi.Core.Beads;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>The backlog of one project, or the reason that bd gave none.</summary>
/// <param name="Answered">True when bd listed the beads.</param>
/// <param name="Message">Empty when bd answered; otherwise a message for the person.</param>
/// <param name="GaveUp">True when the app stopped waiting on bd, so this read may still be running.</param>
public sealed record BacklogOutcome(bool Answered, string Message, Backlog Backlog, bool GaveUp)
{
    private static readonly Backlog Empty = new([], [], new Dictionary<string, IReadOnlyList<string>>());

    public static BacklogOutcome Answer(Backlog backlog) => new(true, string.Empty, backlog, false);

    public static BacklogOutcome Failure(string message) => new(false, message, Empty, false);

    public static BacklogOutcome Abandoned(string message) => new(false, message, Empty, true);
}

/// <summary>
/// Reads the backlog of one project. It takes three reads: every bead, the beads that bd calls
/// ready, and the beads that bd calls blocked. Only the list of beads is essential; without the
/// other two the board still shows every bead, with the status that bd itself printed.
/// </summary>
public sealed class BacklogReader
{
    private readonly BdAdapter adapter;

    public BacklogReader(BdAdapter adapter)
    {
        this.adapter = adapter;
    }

    public async Task<BacklogOutcome> ReadAsync(ProjectPath project)
    {
        var listed = await adapter.ListAsync(project);
        if (!listed.Answered)
        {
            return listed.GaveUp
                ? BacklogOutcome.Abandoned(listed.Message)
                : BacklogOutcome.Failure(listed.Message);
        }

        var ready = await adapter.ReadyAsync(project);
        var blocked = await adapter.BlockedAsync(project);

        return BacklogOutcome.Answer(new Backlog(
            [.. listed.Records.Select(Bead.From)],
            [.. ready.Records.Select(record => record.Text(BeadFields.IdNames))],
            BlockersIn(blocked.Records)));
    }

    private static IReadOnlyDictionary<string, IReadOnlyList<string>> BlockersIn(
        IReadOnlyList<BeadRecord> blocked)
    {
        var blockers = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal);
        foreach (var record in blocked)
        {
            var id = record.Text(BeadFields.IdNames);
            if (id.Length > 0)
            {
                blockers[id] = record.Strings(BeadFields.BlockedByNames);
            }
        }

        return blockers;
    }
}
