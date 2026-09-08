namespace TracerUi.Core.Boards;

/// <summary>One bead on the board, with its status already resolved and its place in the tree.</summary>
/// <param name="Depth">The count of rows above this one in the tree. The title cell indents by it.</param>
/// <param name="Branch">
/// This bead and every bead below it that the board shows, in draw order. A bead that holds nothing
/// is a branch of one. The branch tick of the row takes them together.
/// </param>
public sealed record BoardRow(Bead Bead, BeadStatus Status, int Depth, IReadOnlyList<string> Branch)
{
    /// <summary>
    /// The count of the beads below this row that the board shows. The branch holds this bead too,
    /// so the count is one less than the branch, and a row that holds nothing says zero.
    /// </summary>
    public int Held => Branch.Count - 1;
}

/// <summary>
/// The beads of one project, as a tree. An epic is a row, and the beads that it holds are rows under
/// it, at any depth. The rows of the tree come in draw order. The beads that no epic holds, and that
/// hold no bead of their own, come after them, under the Unparented row.
/// </summary>
public sealed record Board(IReadOnlyList<BoardRow> Rows, IReadOnlyList<BoardRow> Unparented)
{
    /// <summary>The name of the row that gathers every bead which no epic holds.</summary>
    public const string UnparentedTitle = "Unparented";

    /// <summary>The indent of a bead under the Unparented row, which stands one step above it.</summary>
    public const int UnparentedDepth = 1;

    /// <summary>
    /// The count of the beads under the Unparented row. No bead sits behind that row, so the count
    /// is the whole of it, and the filter already took the beads that the board hides.
    /// </summary>
    public int UnparentedHeld => Unparented.Count;

    public bool IsEmpty => Rows.Count == 0 && Unparented.Count == 0;

    /// <summary>Every row of the board, the tree first and the Unparented beads after it.</summary>
    public IEnumerable<BoardRow> EveryRow => Rows.Concat(Unparented);
}
