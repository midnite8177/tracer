using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Boards;

/// <summary>
/// The backlog of one project, or the reason that bd gave none. It is one of three cases, so that no
/// outcome is both an answer and a give-up: bd listed the beads, bd failed, or the app stopped
/// waiting on bd.
/// </summary>
public abstract record BacklogOutcome
{
    private static readonly Backlog Empty = new([], [], BacklogReader.NoBlockers);

    private BacklogOutcome()
    {
    }

    /// <summary>True when bd listed the beads.</summary>
    public bool Answered => this is Given;

    /// <summary>True when bd did not answer in time, so the app gave up on the read.</summary>
    public bool GaveUp => this is Abandoned;

    /// <summary>The backlog that bd listed, or an empty one when bd listed none.</summary>
    public Backlog Backlog => this is Given given ? given.Listed : Empty;

    /// <summary>Empty when bd answered; otherwise a message for the person.</summary>
    public string Message => this switch
    {
        Failed failed => failed.Reason,
        Abandoned abandoned => abandoned.Reason,
        _ => string.Empty,
    };

    /// <summary>The outcome that follows from a list that bd did not answer: it failed, or the app gave up.</summary>
    internal static BacklogOutcome Unanswered(BdOutcome listed) =>
        listed.GaveUp ? new Abandoned(listed.Message) : new Failed(listed.Message);

    /// <summary>bd listed the beads.</summary>
    public sealed record Given(Backlog Listed) : BacklogOutcome;

    /// <summary>bd did not list the beads, or the app could not read them.</summary>
    public sealed record Failed(string Reason) : BacklogOutcome;

    /// <summary>bd did not answer in time, so the app stopped the read.</summary>
    public sealed record Abandoned(string Reason) : BacklogOutcome;
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
            return BacklogOutcome.Unanswered(listed);
        }

        var beads = listed.Records.Select(Bead.From).ToList();
        if (ReadyIdsDerivedFromTheList(listed.Records, beads) is { } derived)
        {
            return new BacklogOutcome.Given(new Backlog(beads, derived, NoBlockers));
        }

        var ready = await adapter.ReadyAsync(project);
        var blocked = await adapter.BlockedAsync(project);

        return new BacklogOutcome.Given(new Backlog(
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
