using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Boards;

/// <summary>
/// What one read for the detail page gave. It is one of three cases, so that no read is both a bead
/// and a give-up: the bead in full, the reason that bd gave none, or the app stopping its wait on
/// bd. A read that gave the bead carries the backlog that the page offers as the far end of a move
/// or of a dependency edge. The backlog belongs to the project and not to the bead, so it travels
/// beside the bead and not inside it.
/// </summary>
public abstract record BeadDetailRead
{
    private BeadDetailRead()
    {
    }

    /// <summary>True when bd did not answer in time, so the app gave up on the read.</summary>
    public bool GaveUp => this is Abandoned;

    /// <summary>Empty when bd gave the bead; otherwise a message for the person.</summary>
    public string Message => this switch
    {
        Failed failed => failed.Reason,
        Abandoned abandoned => abandoned.Reason,
        _ => string.Empty,
    };

    /// <summary>The read that follows from a show that bd did not answer: it failed, or the app gave up.</summary>
    internal static BeadDetailRead Unanswered(BdOutcome shown) =>
        shown.GaveUp ? new Abandoned(shown.Message) : new Failed(shown.Message);

    /// <summary>bd gave the bead, and the read carries the backlog of its project beside it.</summary>
    public sealed record Given(BeadDetail Detail, Backlog Backlog) : BeadDetailRead
    {
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
                .Concat(Detail.Bead.Labels)
                .Where(label => label.Length > 0)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Order(StringComparer.Ordinal)];
    }

    /// <summary>bd gave no bead, in the words that a page shows a person.</summary>
    public sealed record Failed(string Reason) : BeadDetailRead;

    /// <summary>bd did not answer in time, so the app stopped the read.</summary>
    public sealed record Abandoned(string Reason) : BeadDetailRead;
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
            return BeadDetailRead.Unanswered(shown);
        }

        if (shown.Records.Count == 0)
        {
            return new BeadDetailRead.Failed($"This project has no bead {id}.");
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

        return new BeadDetailRead.Given(
            new BeadDetail(read, backlog.StatusOf(read), facts, told),
            backlog);
    }
}
