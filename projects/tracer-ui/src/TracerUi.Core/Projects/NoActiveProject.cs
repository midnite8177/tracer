namespace TracerUi.Core.Projects;

/// <summary>
/// What a page says in place of itself when no project is active. Every such page opens with the
/// same request and then names what it would have shown, so the request reads the same everywhere.
/// </summary>
public static class NoActiveProject
{
    /// <summary>The first sentence of every such page, which each page follows with its own.</summary>
    public const string Ask = "Select a project first.";
}
