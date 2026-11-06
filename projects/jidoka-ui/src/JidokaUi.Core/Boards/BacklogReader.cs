using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Boards;

/// <summary>The backlog of one project, or the reason that bd gave none.</summary>
/// <param name="Answered">True when bd listed the beads.</param>
/// <param name="Message">Empty when bd answered; otherwise a message for the person.</param>
/// <param name="GaveUp">True when bd did not answer in time, so the app gave up on the read.</param>
public sealed record BacklogOutcome(bool Answered, string Message, Backlog Backlog, bool GaveUp)
{
    private static readonly Backlog Empty = new([], [], BacklogReader.NoBlockers);

    public static BacklogOutcome Answer(Backlog backlog) => new(true, string.Empty, backlog, false);

    public static BacklogOutcome Failure(string message) => new(false, message, Empty, false);

    public static BacklogOutcome Abandoned(string message) => new(false, message, Empty, true);
}

/// <summary>
/// Reads the backlog of one project. The list of every bead is essential; without the beads that bd
/// calls ready and the beads that bd calls blocked the board still shows every bead, with the status
/// that bd itself printed. A list that counts what each unfinished bead waits on, and finds none
/// that waits, already says which beads are ready and that none is blocked, so the reader derives
/// the ready set from the list and the read costs one call. Any other list takes two more reads,
/// because bd's list prints the count of what a bead waits on and never which of those beads are
/// still open.
/// </summary>
public sealed class BacklogReader
{
    internal static readonly IReadOnlyDictionary<string, IReadOnlyList<string>> NoBlockers =
        new Dictionary<string, IReadOnlyList<string>>();

    private static readonly string[] ReadyStatuses = [StoredStatus.Open, StoredStatus.InProgress];

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

        var beads = listed.Records.Select(Bead.From).ToList();
        if (ReadyIdsDerivedFromTheList(listed.Records, beads) is { } derived)
        {
            return BacklogOutcome.Answer(new Backlog(beads, derived, NoBlockers));
        }

        var ready = await adapter.ReadyAsync(project);
        var blocked = await adapter.BlockedAsync(project);

        return BacklogOutcome.Answer(new Backlog(
            beads,
            [.. ready.Records.Select(record => record.Text(BeadFields.IdNames))],
            BlockersIn(blocked.Records)));
    }

    private static IReadOnlyList<string>? ReadyIdsDerivedFromTheList(
        IReadOnlyList<BeadRecord> records,
        IReadOnlyList<Bead> beads)
    {
        var ready = new List<string>();
        for (var index = 0; index < beads.Count; index++)
        {
            var bead = beads[index];
            if (bead.IsClosed)
            {
                continue;
            }

            var record = records[index];
            var settled = bead.Status.Length > 0
                && record.NullableNumber(BeadFields.DependencyCountNames) == 0
                && record.Text(BeadFields.DeferredUntilNames).Length == 0;
            if (!settled)
            {
                return null;
            }

            if (ReadyStatuses.Contains(bead.Status))
            {
                ready.Add(bead.Id);
            }
        }

        return ready;
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
