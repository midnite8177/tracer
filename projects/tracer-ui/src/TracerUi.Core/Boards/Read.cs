namespace TracerUi.Core.Boards;

/// <summary>
/// What one read of bd gave: the thing it read, or the reason it read none.
/// </summary>
public abstract record Read<T>
    where T : notnull
{
    // Closes the hierarchy: without it another assembly could add a third case, and every page
    // that tests for Given and Unread alone would fall through it and draw nothing.
    private Read()
    {
    }

    /// <summary>An empty value is still a read that answered.</summary>
    public sealed record Given(T Value) : Read<T>;

    /// <summary>The reason, in the words that a page shows a person.</summary>
    public sealed record Unread(string Reason) : Read<T>;
}
