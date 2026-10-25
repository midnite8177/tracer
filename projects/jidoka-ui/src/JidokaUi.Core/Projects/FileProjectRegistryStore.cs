using System.Diagnostics;
using System.Text.Json;
using JidokaUi.Core.Boards;

namespace JidokaUi.Core.Projects;

/// <summary>A registry that one JSON file on disk holds.</summary>
public sealed class FileProjectRegistryStore : IProjectRegistryStore
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    /// <summary>How long an update waits for another one to let go of the registry.</summary>
    public static readonly TimeSpan LockTimeout = TimeSpan.FromSeconds(2);

    private static readonly TimeSpan RetryInterval = TimeSpan.FromMilliseconds(20);

    private readonly string filePath;
    private readonly TimeSpan lockTimeout;

    public FileProjectRegistryStore(string filePath, TimeSpan lockTimeout)
    {
        this.filePath = filePath;
        this.lockTimeout = lockTimeout;
    }

    public ProjectRegistry Load()
    {
        if (!File.Exists(filePath))
        {
            return ProjectRegistry.Empty;
        }

        var file = JsonSerializer.Deserialize<RegistryFile>(ReadTheFile(), SerializerOptions);
        return file is null ? ProjectRegistry.Empty : ToRegistry(file);
    }

    // Lets an update move a new file over this one while the read runs. Windows refuses to replace a
    // file that a reader opened without FileShare.Delete.
    private string ReadTheFile()
    {
        using var stream = new FileStream(filePath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
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
                Type: filter.Type,
                Priority: filter.Priority,
                Label: filter.Label,
                Epic: filter.Epic,
                Text: filter.Text ?? string.Empty,
                RequiresHumanLabel: filter.RequiresHumanLabel,
                RequiresNoDemoLine: filter.RequiresNoDemoLine,
                ShowDeferred: filter.ShowDeferred,
                ShowClosed: filter.ShowClosed);

    /// <summary>
    /// Reads the registry, applies the change, and writes what the change gives, while it holds a lock
    /// that every store over this file takes.
    /// </summary>
    /// <remarks>
    /// The lock is a separate file beside the registry, and nothing renames it. Each write goes to a
    /// temporary file that then moves over the registry, so a read never sees half a file. That move
    /// would carry off a lock held on the registry file itself.
    /// </remarks>
    public RegistryUpdate Update(Func<ProjectRegistry, ProjectRegistry?> change)
    {
        CreateTheDirectory();
        using var held = TryTakeTheLock();
        if (held is null)
        {
            return RegistryUpdate.Busy;
        }

        if (change(Load()) is not { } changed)
        {
            return RegistryUpdate.Unchanged;
        }

        Write(changed);
        return RegistryUpdate.Written;
    }

    /// <summary>
    /// Copies the earlier registry file over byte for byte when this store's file does not exist, under the
    /// lock that every update takes. The earlier file stays as it is.
    /// </summary>
    /// <remarks>
    /// The existence of this store's file decides, never its content, so a registry that names no project
    /// still keeps the earlier one out.
    /// </remarks>
    public RegistryUpdate CopyFromWhenAbsent(string earlierFilePath)
    {
        if (HasNothingToCopy(earlierFilePath))
        {
            return RegistryUpdate.Unchanged;
        }

        CreateTheDirectory();
        using var held = TryTakeTheLock();
        if (held is null)
        {
            return RegistryUpdate.Busy;
        }

        if (HasNothingToCopy(earlierFilePath))
        {
            return RegistryUpdate.Unchanged;
        }

        var temporary = filePath + ".tmp";
        File.Copy(earlierFilePath, temporary, overwrite: true);
        File.Move(temporary, filePath, overwrite: true);
        return RegistryUpdate.Written;
    }

    private bool HasNothingToCopy(string earlierFilePath) =>
        File.Exists(filePath) || !File.Exists(earlierFilePath);

    private void CreateTheDirectory()
    {
        var directory = Path.GetDirectoryName(filePath);
        if (!string.IsNullOrEmpty(directory))
        {
            Directory.CreateDirectory(directory);
        }
    }

    // Windows refuses a second handle that FileShare.None guards, and .NET on macOS and Linux takes an
    // exclusive flock for it, so either way the open throws while another handle holds the file.
    private FileStream? TryTakeTheLock()
    {
        var waited = Stopwatch.StartNew();
        while (true)
        {
            try
            {
                return new FileStream(filePath + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            }
            catch (IOException) when (waited.Elapsed >= lockTimeout)
            {
                return null;
            }
            catch (IOException)
            {
                Thread.Sleep(RetryInterval);
            }
        }
    }

    private void Write(ProjectRegistry registry)
    {
        var temporary = filePath + ".tmp";
        File.WriteAllText(temporary, JsonSerializer.Serialize(registry, SerializerOptions));
        File.Move(temporary, filePath, overwrite: true);
    }
}
