namespace TracerUi.Core.Projects;

/// <summary>
/// One project of the registry, as the project picker shows it.
/// </summary>
/// <remarks>
/// The mark carries a fact about the whole registry, not about the one project, so only the
/// catalog can set it. A picker that shows a marked entry must show the project path, because a
/// directory name that two projects carry names neither of them.
/// </remarks>
public sealed record ProjectEntry(ProjectPath Path, bool SharesItsName)
{
    /// <summary>The name of the directory of this project.</summary>
    public string DirectoryName => Path.DirectoryName;

    /// <summary>What a list of projects shows for this entry: the directory name, or the whole path
    /// when another project carries that same name.</summary>
    public string Name => SharesItsName ? Path.Value : DirectoryName;
}
