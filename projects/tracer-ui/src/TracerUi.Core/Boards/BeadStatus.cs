namespace TracerUi.Core.Boards;

/// <summary>What a bead waits for. The board resolves one of these for every row.</summary>
public enum BeadStatusKind
{
    /// <summary>A person must decide something before the work goes on.</summary>
    NeedsYou,

    /// <summary>The person put the bead off until later.</summary>
    Deferred,

    /// <summary>A session claimed the bead.</summary>
    InProgress,

    /// <summary>Nothing blocks the bead, so it can be worked now.</summary>
    Ready,

    /// <summary>Another bead must close first.</summary>
    Blocked,

    /// <summary>Whatever bd itself called the bead, for example open or closed.</summary>
    AsBdSaysIt,

    /// <summary>
    /// This backlog does not hold the bead, so it knows neither the stored status, nor the labels,
    /// nor whether the bead is ready. A row of that bead says so instead of drawing a status.
    /// </summary>
    NotInThisBacklog,
}

/// <summary>The resolved status of one bead, and the words that the board shows for it.</summary>
/// <param name="Kind">Which of the states the bead is in.</param>
/// <param name="Detail">The assignee of a bead in progress, or the raw status that bd printed.</param>
/// <param name="Blockers">The titles of the beads that block this one, in the order bd gave them.</param>
public sealed record BeadStatus(BeadStatusKind Kind, string Detail, IReadOnlyList<string> Blockers)
{
    // How many blockers the board names before it counts the rest.
    private const int BlockersNamed = 2;

    /// <summary>
    /// The one name that the board draws this status as. It is a name and not a color, so the
    /// statuses stay in one place and no page states a color: see ADR 0006. Each kind names itself
    /// here, and the last arm answers the compiler alone, so a kind with no name is a visible gap.
    /// </summary>
    public string Appearance => Kind switch
    {
        BeadStatusKind.NeedsYou => "needs-you",
        BeadStatusKind.Deferred => "deferred",
        BeadStatusKind.InProgress => "in-progress",
        BeadStatusKind.Ready => "ready",
        BeadStatusKind.Blocked => "blocked",
        BeadStatusKind.AsBdSaysIt => "stored",
        BeadStatusKind.NotInThisBacklog => "unknown",
        _ => throw new ArgumentOutOfRangeException(nameof(Kind), Kind, "This status has no appearance."),
    };

    /// <summary>True when bd closed the bead, so it waits for nothing and a list strikes it out.</summary>
    public bool IsClosed => Kind == BeadStatusKind.AsBdSaysIt && Detail == StoredStatus.Closed;

    public string Text => Kind switch
    {
        BeadStatusKind.NeedsYou => "needs you",
        BeadStatusKind.Deferred => "deferred",
        BeadStatusKind.InProgress => $"in progress ({Detail})",
        BeadStatusKind.Ready => "ready",
        BeadStatusKind.Blocked => $"blocked by {NamedBlockers}",
        BeadStatusKind.NotInThisBacklog => "not in this project",
        _ => Detail,
    };

    private string NamedBlockers
    {
        get
        {
            var named = string.Join(", ", Blockers.Take(BlockersNamed));
            var rest = Blockers.Count - BlockersNamed;
            return rest > 0 ? $"{named} +{rest}" : named;
        }
    }
}
