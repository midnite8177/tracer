namespace TracerUi.Tests;

/// <summary>The bound on a test's wait for a signal from the code under test.</summary>
public static class Signals
{
    /// <summary>Long enough for a slow machine, short enough to fail fast.</summary>
    public static readonly TimeSpan LongEnough = TimeSpan.FromSeconds(10);
}
