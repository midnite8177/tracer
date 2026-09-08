namespace TracerUi.Core.Boards;

/// <summary>
/// A set of bead ids that a person built by hand: the beads of a selection, the rows that a person
/// collapsed. It holds ids and not beads, because the board reads its beads again after every write,
/// and it keeps no order of its own: the board gives the order in which it draws them.
/// </summary>
public sealed class IdSet
{
    private readonly HashSet<string> ids = new(StringComparer.Ordinal);

    /// <summary>The ids that this set holds. The board gives them their order, not this set.</summary>
    public IReadOnlyCollection<string> Ids => ids;

    public int Count => ids.Count;

    public bool IsEmpty => ids.Count == 0;

    public bool Holds(string id) => ids.Contains(id);

    /// <summary>Adds the id when the set lacks it, and drops it when the set holds it.</summary>
    public void Toggle(string id)
    {
        if (!ids.Remove(id))
        {
            ids.Add(id);
        }
    }

    /// <summary>Adds every one of these ids, so that a group joins the set in one action.</summary>
    public void TakeAll(IEnumerable<string> some) => ids.UnionWith(some);

    public void DropAll(IEnumerable<string> some) => ids.ExceptWith(some);

    /// <summary>
    /// Takes every one of these ids, and drops them all when the set already holds each of them, so
    /// that a second press of one tick undoes the first.
    /// </summary>
    public void ToggleAll(IReadOnlyCollection<string> some)
    {
        if (HoldsAll(some))
        {
            DropAll(some);
        }
        else
        {
            TakeAll(some);
        }
    }

    /// <summary>
    /// True when the set already holds every one of these ids. An empty group holds nothing, so it
    /// gives false, and a tick over no rows reads as unticked.
    /// </summary>
    public bool HoldsAll(IReadOnlyCollection<string> some) =>
        some.Count > 0 && some.All(ids.Contains);

    /// <summary>
    /// Drops every id of this set that is not among these. It walks the whole of them, so the
    /// caller pays for the count it passes.
    /// </summary>
    public void KeepOnly(IEnumerable<string> some) => ids.IntersectWith(some);

    public void Clear() => ids.Clear();
}
