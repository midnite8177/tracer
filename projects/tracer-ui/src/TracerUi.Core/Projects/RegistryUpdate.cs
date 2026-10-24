namespace TracerUi.Core.Projects;

/// <summary>What one update of the registry did.</summary>
public enum RegistryUpdate
{
    /// <summary>The change gave a new registry, and the store wrote it.</summary>
    Written,

    /// <summary>The change left the registry as it was, so the store wrote nothing.</summary>
    Unchanged,

    /// <summary>
    /// Another update held the registry for longer than the store waits, so the store neither read
    /// nor wrote it.
    /// </summary>
    Busy,
}
