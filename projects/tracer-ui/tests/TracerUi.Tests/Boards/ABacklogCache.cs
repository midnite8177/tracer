using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Tests.Beads;

namespace TracerUi.Tests.Boards;

/// <summary>A cache over a bd that answers nothing, for a test that watches the change alone.</summary>
public static class ABacklogCache
{
    /// <summary>Long enough that a slow machine still reports a write, short enough to fail fast.</summary>
    public static readonly TimeSpan LongEnough = TimeSpan.FromSeconds(10);

    /// <summary>How long to wait before reading a count that a test proves stays where it is.</summary>
    /// <remarks>
    /// A test that proves no further invalidation arrives has to outlive every chance of one, so it
    /// waits several quiet periods. A shorter wait passes for the wrong reason, because the stray
    /// invalidation lands after the assertion has already read the count.
    /// </remarks>
    public static TimeSpan LongEnoughForAStrayInvalidationToLand(TimeSpan quietPeriod) =>
        quietPeriod * 6;

    public static BacklogCache OverASilentBd()
    {
        var adapter = new BdAdapter(new FakeBd(), TimeProvider.System);
        return new BacklogCache(new BacklogReader(adapter), adapter);
    }
}
