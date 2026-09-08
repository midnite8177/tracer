using System.Text.Json;
using TracerUi.Core.Boards;

namespace TracerUi.Core.Projects;

/// <summary>A registry that one JSON file on disk holds.</summary>
public sealed class FileProjectRegistryStore : IProjectRegistryStore
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    private readonly string filePath;

    public FileProjectRegistryStore(string filePath)
    {
        this.filePath = filePath;
    }

    public ProjectRegistry Load()
    {
        if (!File.Exists(filePath))
        {
            return ProjectRegistry.Empty;
        }

        var json = File.ReadAllText(filePath);
        var file = JsonSerializer.Deserialize<RegistryFile>(json, SerializerOptions);
        return file is null ? ProjectRegistry.Empty : ToRegistry(file);
    }

    // The shape of the registry file. Every list is absent until a version of the app writes it, so
    // a file that an earlier version wrote names the projects alone.
    private sealed record RegistryFile(
        IReadOnlyList<ProjectPath?>? Projects,
        IReadOnlyList<SavedFilterFile?>? SavedFilters);

    private sealed record SavedFilterFile(ProjectPath? Project, string? Name, BoardFilterFile? Filter);

    private sealed record BoardFilterFile(
        string? Status,
        string? Type,
        string? Priority,
        string? Label,
        string? Epic,
        string? Text,
        bool RequiresHumanLabel,
        bool RequiresNoDemoLine,
        bool ShowDeferred,
        bool ShowClosed);

    private static ProjectRegistry ToRegistry(RegistryFile file) =>
        new(ToProjects(file.Projects ?? []), ToSavedFilters(file.SavedFilters ?? []));

    // Nothing for a project that the file writes as nothing: it names no directory to read.
    private static IReadOnlyList<ProjectPath> ToProjects(IReadOnlyList<ProjectPath?> projects) =>
        [.. projects.OfType<ProjectPath>()];

    private static IReadOnlyList<SavedFilter> ToSavedFilters(IReadOnlyList<SavedFilterFile?> saved) =>
        [.. saved.Select(ToSavedFilter).OfType<SavedFilter>()];

    // Nothing for a saved filter that names no project or no name: it reaches no project, and it
    // answers to nothing the person can pick.
    private static SavedFilter? ToSavedFilter(SavedFilterFile? saved) =>
        saved is { Project: { } project, Name: { } name }
            ? new SavedFilter(project, name, ToBoardFilter(saved.Filter))
            : null;

    private static BoardFilter ToBoardFilter(BoardFilterFile? filter) =>
        filter is null
            ? BoardFilter.Everything
            : new BoardFilter(
                Status: filter.Status ?? string.Empty,
                Type: filter.Type ?? string.Empty,
                Priority: filter.Priority ?? string.Empty,
                Label: filter.Label ?? string.Empty,
                Epic: filter.Epic ?? string.Empty,
                Text: filter.Text ?? string.Empty,
                RequiresHumanLabel: filter.RequiresHumanLabel,
                RequiresNoDemoLine: filter.RequiresNoDemoLine,
                ShowDeferred: filter.ShowDeferred,
                ShowClosed: filter.ShowClosed);

    public void Save(ProjectRegistry registry)
    {
        var directory = Path.GetDirectoryName(filePath);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }

        File.WriteAllText(filePath, JsonSerializer.Serialize(registry, SerializerOptions));
    }
}
