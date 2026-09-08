namespace TracerUi.Core.Boards;

/// <summary>
/// Where a press on a row started, and whether the press that ends somewhere else is a drag.
/// A row of the board and a row of the needs-you view both open a bead on a click, and a drag
/// across the text of a row ends in a click too, so the row asks this before it opens anything.
/// </summary>
public sealed class RowPress
{
    /// <summary>
    /// How far the pointer travels before a press reads as a drag. A hand that holds a mouse moves
    /// it a little on every click, so a press under this distance is still a click.
    /// </summary>
    public const double DragDistance = 4;

    private (double X, double Y)? start;

    /// <summary>Holds where the pointer went down, which the release reads.</summary>
    public void StartedAt(double x, double y) => start = (x, y);

    /// <summary>
    /// True when the pointer traveled far enough between the press and this release to read as a
    /// drag. It forgets the press, so the next release asks about the next press alone. A release
    /// that follows no press is a click, because a keyboard and a touch both give one.
    /// </summary>
    public bool Dragged(double x, double y)
    {
        var from = start;
        start = null;
        return from is not null && double.Hypot(x - from.Value.X, y - from.Value.Y) > DragDistance;
    }
}
