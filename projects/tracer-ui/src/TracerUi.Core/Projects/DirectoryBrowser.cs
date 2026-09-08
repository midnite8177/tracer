namespace TracerUi.Core.Projects;

/// <summary>Reads the filesystem for the widget that picks a repository.</summary>
public static class DirectoryBrowser
{
    public static DirectoryListing Browse(string path)
    {
        var current = new DirectoryInfo(path);
        return new DirectoryListing(current.FullName, current.Parent?.FullName, SubdirectoriesOf(current));
    }

    // Gives an empty list when the person is not permitted to read the directory.
    private static IReadOnlyList<DirectoryEntry> SubdirectoriesOf(DirectoryInfo current)
    {
        try
        {
            return current
                .EnumerateDirectories()
                .Select(directory => new DirectoryEntry(
                    directory.Name,
                    directory.FullName,
                    Directory.Exists(Path.Combine(directory.FullName, ProjectPathValidator.BeadsDirectoryName))))
                .OrderBy(entry => entry.Name, StringComparer.OrdinalIgnoreCase)
                .ToList();
        }
        catch (Exception exception) when (exception is UnauthorizedAccessException or IOException)
        {
            return [];
        }
    }
}
