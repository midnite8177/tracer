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

    /// <summary>Opens every row again.</summary>
    public void Clear()
    {
        collapsed.Clear();
        unparentedCollapsed = false;
    }

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
