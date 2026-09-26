namespace TracerUi.Core.Boards;

/// <summary>
/// The rows of the board that a person collapsed, so that the beads below them leave the screen. It
/// starts empty, so a person who presses nothing reads the whole tree.
/// </summary>
public sealed class CollapsedRows
{
    private readonly IdSet collapsed = new();
    private bool unparentedCollapsed;

    /// <summary>True when this row is collapsed, so the board hides the beads below it.</summary>
    public bool Holds(string id) => collapsed.Holds(id);

    /// <summary>Collapses the row when it is open, and opens it when it is collapsed.</summary>
    public void Toggle(string id) => collapsed.Toggle(id);

    /// <summary>
    /// True when a person collapsed the Unparented row, so the loose beads leave the screen. No bead
    /// sits behind that row, so it carries a state of its own and no id.
    /// </summary>
    public bool HoldsUnparented => unparentedCollapsed;

    /// <summary>Collapses the Unparented row when it is open, and opens it when it is collapsed.</summary>
    public void ToggleUnparented() => unparentedCollapsed = !unparentedCollapsed;

    /// <summary>
    /// Collapses every row of this board that holds beads, and the Unparented row when the board
    /// draws it. It takes every row of the tree and not only the drawn ones, so a row below a
    /// collapsed row collapses too and stays collapsed when a person opens the row above it. It
    /// takes the board at the press, so a row that arrives later arrives open.
    /// </summary>
    public void CollapseAll(Board board)
    {
        collapsed.TakeAll(board.Rows.Where(row => row.HoldsBeads).Select(row => row.Bead.Id));
        unparentedCollapsed = unparentedCollapsed || board.Unparented.Count > 0;
    }

    /// <summary>
    /// True when every row of this board that holds beads is collapsed, and the Unparented row too
    /// when the board draws it, so a press of Collapse all has nothing left to collapse. A board
    /// where no row holds a bead gives true for the same reason.
    /// </summary>
    public bool LeavesNothingToCollapse(Board board) =>
        (unparentedCollapsed || board.Unparented.Count == 0)
        && board.Rows.Where(row => row.HoldsBeads).All(row => collapsed.Holds(row.Bead.Id));

    /// <summary>
    /// True when any row is collapsed, so Expand all has a row to open. It counts a row that a
    /// filter hides now, because Expand all opens that row too.
    /// </summary>
    public bool HoldsAny => !collapsed.IsEmpty || unparentedCollapsed;

    /// <summary>Opens every row again, a row that a filter hides now as well.</summary>
    public void OpenAll()
    {
        collapsed.Clear();
        unparentedCollapsed = false;
    }

    /// <summary>
    /// Opens every collapsed row whose bead is not among these, so a bead that left the backlog
    /// leaves no collapsed row behind. The caller passes the beads of the whole backlog and not only
    /// the ones that the filter shows, because a row that a filter hides stays collapsed.
    /// </summary>
    public void KeepOnly(IEnumerable<string> ids) => collapsed.KeepOnly(ids);

    /// <summary>
    /// The rows that the board draws, in the order that it draws them: these rows, minus the beads
    /// below a collapsed row. A collapsed row itself stays. It takes the rows in the draw order of a
    /// board, where a row comes before the branch below it, because it hides a branch as it passes
    /// the row that carries it.
    /// </summary>
    public IReadOnlyList<BoardRow> Draws(IReadOnlyList<BoardRow> rows)
    {
        var hidden = new HashSet<string>(StringComparer.Ordinal);
        var drawn = new List<BoardRow>();
        foreach (var row in rows)
        {
            if (hidden.Contains(row.Bead.Id))
            {
                continue;
            }

            drawn.Add(row);
            if (collapsed.Holds(row.Bead.Id))
            {
                hidden.UnionWith(row.Branch.Where(id => !string.Equals(id, row.Bead.Id, StringComparison.Ordinal)));
            }
        }

        return drawn;
    }

    /// <summary>
    /// The loose beads that the board draws under the Unparented row: all of them, or none while a
    /// person holds that row collapsed. The row itself stays either way.
    /// </summary>
    public IReadOnlyList<BoardRow> DrawsUnparented(IReadOnlyList<BoardRow> unparented) =>
        unparentedCollapsed ? [] : unparented;
}
