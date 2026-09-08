namespace TracerUi.Core.Boards;

/// <summary>
/// Every bead of one project, together with what bd said is ready and what is blocked. It answers
/// the questions that a board asks, and it holds no state of the UI.
/// </summary>
/// <param name="Beads">Every bead of the project, whatever its status.</param>
/// <param name="ReadyIds">The ids of the beads that bd calls ready.</param>
/// <param name="Blockers">For each blocked bead, the ids of the beads that block it.</param>
public sealed record Backlog(
    IReadOnlyList<Bead> Beads,
    IReadOnlyList<string> ReadyIds,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Blockers)
{
    private const string NoAssignee = "?";

    private readonly HashSet<string> ready = [.. ReadyIds];

    private readonly Dictionary<string, Bead> byId =
        Beads.Where(bead => bead.Id.Length > 0)
            .GroupBy(bead => bead.Id, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.First(), StringComparer.Ordinal);

    /// <summary>
    /// The types that the beads of this backlog use, once each, in ordinal order. Two spellings
    /// that differ only in case are one type, because the filter matches a type without its case.
    /// </summary>
    public IReadOnlyList<string> Types =>
        [.. Beads.Select(bead => bead.Type)
            .Where(type => type.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.Ordinal)];

    /// <summary>
    /// The labels that the beads of this backlog carry, once each, in ordinal order. Two spellings
    /// that differ only in case are one label, because the filter matches a label without its case.
    /// </summary>
    public IReadOnlyList<string> Labels =>
        [.. Beads.SelectMany(bead => bead.Labels)
            .Where(label => label.Length > 0)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Order(StringComparer.Ordinal)];

    /// <summary>
    /// The priorities that the beads of this backlog state, once each, from the most urgent. A bead
    /// that states none carries no priority a person can press, so it names none here either.
    /// </summary>
    public IReadOnlyList<long> Priorities =>
        [.. Beads.Where(bead => bead.HasPriority)
            .Select(bead => bead.Priority)
            .Distinct()
            .Order()];

    /// <summary>The epics of this backlog, in the order that bd gave them.</summary>
    public IReadOnlyList<Bead> Epics => [.. Beads.Where(bead => bead.IsEpic)];

    /// <summary>
    /// The beads that this filter keeps, by priority and then by title. An epic that the filter keeps
    /// is one of them, as it is on a board, where an epic fills a row of its own.
    /// </summary>
    public IReadOnlyList<Bead> BeadsThatMatch(BoardFilter filter) =>
        [.. Beads
            .Where(bead => filter.Shows(bead.Status) && filter.Matches(bead, EpicsAbove(bead)))
            .OrderBy(bead => bead.Priority)
            .ThenBy(bead => bead.Title, StringComparer.Ordinal)];

    /// <summary>
    /// The board that this filter asks for: a tree in draw order, and the beads of the Unparented
    /// row after it. An epic is a row, and the beads that it holds are rows under it, at any depth.
    /// The board keeps an epic row when the filter keeps the epic, or when it keeps a bead below it.
    /// </summary>
    public Board ToBoard(BoardFilter filter)
    {
        var tree = new TreeOfBeads(
            ChildrenOfEachEpic(),
            [.. BeadsThatMatch(filter).Select(bead => bead.Id)]);
        var roots = Beads.Where(IsARoot).Where(tree.Shows).ToList();

        var rows = new List<BoardRow>();
        foreach (var root in Sorted(roots.Where(bead => bead.IsEpic || tree.HoldsABead(bead.Id))))
        {
            Draw(root, 0, tree, rows);
        }

        var unparented = Sorted(roots.Where(bead => !bead.IsEpic && !tree.HoldsABead(bead.Id)))
            .Select(bead => new BoardRow(bead, StatusOf(bead), Board.UnparentedDepth, [bead.Id]));

        return new Board(rows, [.. unparented]);
    }

    // Writes one row and then the rows of every bead below it that the board shows, and answers
    // with the branch that it drew. The beads below come first, because the row of this bead
    // carries the branch that they make.
    private IReadOnlyList<string> Draw(Bead bead, int depth, TreeOfBeads tree, List<BoardRow> into)
    {
        var below = new List<BoardRow>();
        var branch = new List<string> { bead.Id };
        foreach (var child in Sorted(tree.HeldBy(bead.Id).Where(tree.Shows)))
        {
            branch.AddRange(Draw(child, depth + 1, tree, below));
        }

        into.Add(new BoardRow(bead, StatusOf(bead), depth, branch));
        into.AddRange(below);
        return branch;
    }

    // The beads that each epic holds, in the order that bd gave them. A root holds no place here,
    // so the answer is a forest and a walk down it ends.
    private IReadOnlyDictionary<string, IReadOnlyList<Bead>> ChildrenOfEachEpic()
    {
        var children = new Dictionary<string, List<Bead>>(StringComparer.Ordinal);
        foreach (var bead in Beads.Where(bead => !IsARoot(bead)))
        {
            if (!children.TryGetValue(bead.ParentId, out var held))
            {
                held = [];
                children[bead.ParentId] = held;
            }

            held.Add(bead);
        }

        return children.ToDictionary(
            pair => pair.Key,
            pair => (IReadOnlyList<Bead>)pair.Value,
            StringComparer.Ordinal);
    }

    private bool IsARoot(Bead bead) =>
        bead.ParentId.Length == 0
        || !byId.ContainsKey(bead.ParentId)
        // Epics above it that lead back to the bead itself are a cycle, which heads its own tree.
        || EpicsAbove(bead).Contains(bead.Id, StringComparer.Ordinal);

    private IEnumerable<Bead> Sorted(IEnumerable<Bead> beads) =>
        beads
            .OrderBy(bead => ready.Contains(bead.Id) ? 0 : 1)
            .ThenBy(bead => bead.Priority)
            .ThenBy(bead => bead.Title, StringComparer.Ordinal);

    // The beads that each bead of one backlog holds, and the answer to which of them the board draws.
    // One filter builds one of these, so a walk down the tree asks it and asks the filter no more.
    private sealed class TreeOfBeads(
        IReadOnlyDictionary<string, IReadOnlyList<Bead>> children,
        HashSet<string> matched)
    {
        private readonly Dictionary<string, bool> answered = new(StringComparer.Ordinal);

        public IReadOnlyList<Bead> HeldBy(string id) =>
            children.TryGetValue(id, out var held) ? held : [];

        public bool HoldsABead(string id) => children.ContainsKey(id);

        // True when the board draws a row for this bead: the filter keeps the bead itself, or it
        // keeps a bead below it, at any depth, so a filter on a type keeps the epics on the board.
        public bool Shows(Bead bead)
        {
            if (answered.TryGetValue(bead.Id, out var already))
            {
                return already;
            }

            var shows = matched.Contains(bead.Id) || HeldBy(bead.Id).Any(Shows);
            answered[bead.Id] = shows;
            return shows;
        }
    }

    /// <summary>
    /// The status of one bead. A closed bead is closed, whatever else it carries, because it waits
    /// for nobody. Otherwise a bead that needs a person beats a deferred one, which beats one in
    /// progress, which beats a ready one, which beats a blocked one. Anything else is what bd said.
    /// </summary>
    public BeadStatus StatusOf(Bead bead)
    {
        if (bead.IsClosed)
        {
            return new BeadStatus(BeadStatusKind.AsBdSaysIt, StoredStatus.Closed, []);
        }

        if (bead.NeedsYou)
        {
            return new BeadStatus(BeadStatusKind.NeedsYou, string.Empty, []);
        }

        if (bead.Status == StoredStatus.Deferred)
        {
            return new BeadStatus(BeadStatusKind.Deferred, string.Empty, []);
        }

        if (bead.Status == StoredStatus.InProgress)
        {
            var assignee = bead.Assignee.Length > 0 ? bead.Assignee : NoAssignee;
            return new BeadStatus(BeadStatusKind.InProgress, assignee, []);
        }

        if (ready.Contains(bead.Id))
        {
            return new BeadStatus(BeadStatusKind.Ready, string.Empty, []);
        }

        if (Blockers.TryGetValue(bead.Id, out var blockers) && blockers.Count > 0)
        {
            return new BeadStatus(BeadStatusKind.Blocked, string.Empty, [.. blockers.Select(TitleOf)]);
        }

        var raw = bead.Status.Length > 0 ? bead.Status : StoredStatus.Open;
        return new BeadStatus(BeadStatusKind.AsBdSaysIt, raw, []);
    }

    /// <summary>
    /// The beads that must close before this one, with their titles, in the order that bd gave them.
    /// </summary>
    public IReadOnlyList<BeadLink> BlockersOf(Bead bead) => [.. bead.Blockers.Select(LinkTo)];

    /// <summary>
    /// The beads that wait for this one, with their titles, in the order that bd gave them. bd names
    /// only the count, so the backlog reads the edges of every bead to find them.
    /// </summary>
    public IReadOnlyList<BeadLink> DependentsOf(Bead bead) =>
        [.. Beads
            .Where(other => other.Blockers.Contains(bead.Id, StringComparer.Ordinal))
            .Select(other => LinkTo(other.Id))];

    /// <summary>
    /// The beads that this bead holds directly, one level and no deeper: the open ones first, in the
    /// order that the board draws them, and the closed ones after them, because the open ones are
    /// the work that is left. A bead further down belongs to the bead that holds it and not to this
    /// one. A bead that a cycle of epics leads back to heads its own tree, as it does on the board,
    /// so no bead holds it here.
    /// </summary>
    public IReadOnlyList<BeadLink> BeadsHeldBy(Bead bead) =>
        [.. Sorted(Beads.Where(other => !IsARoot(other) && other.ParentId == bead.Id))
            .OrderBy(other => other.IsClosed ? 1 : 0)
            .Select(other => LinkTo(other.Id))];

    /// <summary>The epic that holds this bead, with its title, or null when no epic holds it.</summary>
    public BeadLink? EpicOf(Bead bead) =>
        bead.ParentId.Length > 0 ? LinkTo(bead.ParentId) : null;

    // What this backlog knows of the bead with this id. A bead that it does not hold answers as an
    // unknown one, so the row states nothing that the backlog cannot answer for.
    private BeadLink LinkTo(string id) =>
        byId.TryGetValue(id, out var bead)
            ? new BeadLink(id, TitleOf(id), bead.Type, StatusOf(bead))
            : BeadLink.UnknownTo(id);

    /// <summary>
    /// The epics that hold this bead, from the one that holds it out to the outermost one. A bead
    /// that no epic holds has none. A cycle among the epics ends the walk instead of repeating it.
    /// </summary>
    public IReadOnlyList<string> EpicsAbove(Bead bead)
    {
        var above = new List<string>();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var parentId = bead.ParentId;
        while (parentId.Length > 0 && seen.Add(parentId) && byId.TryGetValue(parentId, out var epic))
        {
            above.Add(parentId);
            parentId = epic.ParentId;
        }

        return above;
    }

    private string TitleOf(string id) =>
        byId.TryGetValue(id, out var bead) && bead.Title.Length > 0 ? bead.Title : id;
}
