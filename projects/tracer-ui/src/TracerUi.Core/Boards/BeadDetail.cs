namespace TracerUi.Core.Boards;

/// <summary>
/// What only the backlog of a project answers about one bead: the epic that holds it, the beads it
/// holds, the beads that block it and the beads it blocks. A page reaches these four together or
/// not at all, because one read of the backlog gives every one of them or none.
/// </summary>
/// <param name="Epic">The epic that holds this bead, or null when no epic holds it.</param>
/// <param name="Held">The beads that this bead holds directly, one level and no deeper.</param>
/// <param name="Blockers">The beads that must close before this one.</param>
/// <param name="Dependents">The beads that wait for this one.</param>
public sealed record BacklogFacts(
    BeadLink? Epic,
    IReadOnlyList<BeadLink> Held,
    IReadOnlyList<BeadLink> Blockers,
    IReadOnlyList<BeadLink> Dependents)
{
    /// <summary>
    /// True when this bead names no bead at all: nothing blocks it, it blocks nothing, and it holds
    /// none. The epic that holds this one is not one of the three, so a bead inside an epic is still
    /// this when it names none itself.
    /// </summary>
    public bool NamesNoBead => Held.Count == 0 && Blockers.Count == 0 && Dependents.Count == 0;
}

/// <summary>
/// One bead as the detail page shows it. The status stands beside the two reads and is not one of
/// them: the reader resolves it against whatever backlog it got, so a bead whose backlog went
/// unread carries the status that bd stored.
/// </summary>
public sealed record BeadDetail(
    Bead Bead,
    BeadStatus Status,
    Read<BacklogFacts> BacklogFacts,
    Read<IReadOnlyList<BeadComment>> Comments);
