namespace TracerUi.Core.Projects;

/// <summary>One subdirectory that the directory browser shows.</summary>
/// <param name="Name">The name of the directory.</param>
/// <param name="Path">The absolute path of the directory.</param>
/// <param name="IsProject">True when the directory holds a .beads directory.</param>
public sealed record DirectoryEntry(string Name, string Path, bool IsProject);

/// <summary>What the directory browser shows for one directory.</summary>
/// <param name="CurrentPath">The directory that the person looks at.</param>
/// <param name="ParentPath">The directory above it, or null at the root of the filesystem.</param>
/// <param name="Directories">The subdirectories, in name order.</param>
/// <param name="Roots">
/// The filesystem roots that the browser can jump to: one for each drive on
/// Windows, or / on other systems.
/// </param>
public sealed record DirectoryListing(
    string CurrentPath,
    string? ParentPath,
    IReadOnlyList<DirectoryEntry> Directories,
    IReadOnlyList<string> Roots);
