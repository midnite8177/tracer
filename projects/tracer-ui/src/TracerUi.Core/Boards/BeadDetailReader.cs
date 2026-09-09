using TracerUi.Core.Beads;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// What one read for the detail page gave: the bead in full or the reason that bd gave none, and
/// the backlog that the page offers as the far end of a move or of a dependency edge. The backlog
/// belongs to the project and not to the bead, so it travels beside the read and not inside it.
/// </summary>
/// <param name="Backlog">
/// The backlog of the project, which answers what a picker of this page offers: the beads by title,
/// the epics, and the labels that the project uses. It is empty when the read gave none.
/// </param>
/// <param name="GaveUp">True when the app stopped waiting on bd, so this read may still be running.</param>
public sealed record BeadDetailRead(
    Read<BeadDetail> Detail,
    Backlog Backlog,
    bool GaveUp)
{
    private static readonly Backlog EmptyBacklog = new([], [], new Dictionary<string, IReadOnlyList<string>>());

    /// <summary>Every bead of the backlog, so that a picker offers them by title.</summary>
    public IReadOnlyList<Bead> Beads => Backlog.Beads;

    /// <summary>Every epic of the backlog, so that a move offers them by title.</summary>
    public IReadOnlyList<Bead> Epics => Backlog.Epics;

    /// <summary>
    /// The labels that the labels picker offers: the vocabulary of the project, and the labels of
    /// this bead beside it. A read that gave no backlog knows the second and not the first, and a
    /// person must still be able to take a label off the bead they are reading.
    /// </summary>
    public IReadOnlyList<string> Labels =>
        [.. Backlog.Labels
            .Concat(Detail is Read<BeadDetail>.Given given ? given.Value.Bead.Labels : [])
            .Where(label => label.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.Ordinal)];

    public static BeadDetailRead Answer(BeadDetail detail, Backlog backlog) =>
        new(new Read<BeadDetail>.Given(detail), backlog, false);

    public static BeadDetailRead Failure(string message) =>
        new(new Read<BeadDetail>.Unread(message), EmptyBacklog, false);

    public static BeadDetailRead Abandoned(string message) =>
        new(new Read<BeadDetail>.Unread(message), EmptyBacklog, true);
}

/// <summary>
/// Reads one bead in full. It takes the show of that bead, its comments, and the backlog of the
/// project. The backlog carries the titles and the ready set, and it is the only place that names
/// the beads which wait for this one, because bd itself gives their count and not their ids.
/// </summary>
public sealed class BeadDetailReader
{
    private readonly BdAdapter adapter;
    private readonly BacklogReader backlogs;

    public BeadDetailReader(BdAdapter adapter, BacklogReader backlogs)
    {
        this.adapter = adapter;
        this.backlogs = backlogs;
    }

    public async Task<BeadDetailRead> ReadAsync(ProjectPath project, string id)
    {
        var bead = new BeadAddress(project, id);
        var shown = await adapter.ShowAsync(bead);
        if (!shown.Answered)
        {
            return shown.GaveUp
                ? BeadDetailRead.Abandoned(shown.Message)
                : BeadDetailRead.Failure(shown.Message);
        }

        if (shown.Records.Count == 0)
        {
            return BeadDetailRead.Failure($"This project has no bead {id}.");
        }

        var read = Bead.From(shown.Records[0]);
        var listed = await backlogs.ReadAsync(project);
        var backlog = listed.Backlog;
        var comments = await adapter.CommentsAsync(bead);

        Read<BacklogFacts> facts = listed.Answered
            ? new Read<BacklogFacts>.Given(new BacklogFacts(
                backlog.EpicOf(read),
                backlog.BeadsHeldBy(read),
                backlog.BlockersOf(read),
                backlog.DependentsOf(read)))
            : new Read<BacklogFacts>.Unread(listed.Message);

        Read<IReadOnlyList<BeadComment>> told = comments.Answered
            ? new Read<IReadOnlyList<BeadComment>>.Given(
                [.. comments.Records.Select(BeadComment.From)])
            : new Read<IReadOnlyList<BeadComment>>.Unread(comments.Message);

        return BeadDetailRead.Answer(
            new BeadDetail(read, backlog.StatusOf(read), facts, told),
            backlog);
    }
}
