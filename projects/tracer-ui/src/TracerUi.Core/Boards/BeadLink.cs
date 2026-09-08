namespace TracerUi.Core.Boards;

/// <summary>
/// One bead that another bead names: its epic, a bead that it holds, a bead that blocks it, or a
/// bead that waits for it. It carries what a bead row draws, so a person reads the row without a
/// second lookup. A backlog that does not hold the bead knows none of it but the id.
/// </summary>
/// <param name="Title">The title of that bead, or its id when this backlog does not hold it.</param>
/// <param name="Type">The type of that bead, or an empty string when this backlog does not hold it.</param>
/// <param name="Status">The resolved status of that bead, which the dot of the row draws.</param>
public sealed record BeadLink(string Id, string Title, string Type, BeadStatus Status)
{
    /// <summary>
    /// The bead with this id, as a backlog that does not hold it knows it: the id in the place of
    /// the title, no type, and a status that says the backlog answers for none of it.
    /// </summary>
    public static BeadLink UnknownTo(string id) =>
        new(id, id, string.Empty, new BeadStatus(BeadStatusKind.NotInThisBacklog, string.Empty, []));
}
