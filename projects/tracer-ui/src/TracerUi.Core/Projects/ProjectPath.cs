using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace TracerUi.Core.Projects;

/// <summary>The absolute path of a repository in the registry.</summary>
/// <remarks>
/// Two paths that name the same directory are equal. macOS and Windows ignore the case of a path,
/// and other systems do not, so the comparison follows the system that runs the app.
/// </remarks>
[JsonConverter(typeof(ProjectPathJsonConverter))]
public sealed class ProjectPath : IEquatable<ProjectPath>
{
    private static readonly StringComparer PathComparer =
        OperatingSystem.IsLinux() ? StringComparer.Ordinal : StringComparer.OrdinalIgnoreCase;

    private ProjectPath(string value)
    {
        Value = value;
    }

    /// <summary>The absolute path, with no trailing directory separator.</summary>
    public string Value { get; }

    /// <summary>The name of the directory itself, which the project picker shows.</summary>
    public string DirectoryName => new DirectoryInfo(Value).Name;

    /// <summary>The directory that holds the beads of this project.</summary>
    public string BeadsDirectory =>
        Path.Combine(Value, ProjectPathValidator.BeadsDirectoryName);

    public static ProjectPath From(string path) =>
        new(Path.TrimEndingDirectorySeparator(Path.GetFullPath(path)));

    /// <summary>
    /// Reads text that a person can edit, such as a path typed on the Add a project page or the
    /// project that an address names. It gives false for text that the system refuses as a path, so
    /// no such text reaches the app as an error.
    /// </summary>
    public static bool TryFrom(string text, [NotNullWhen(true)] out ProjectPath? path)
    {
        try
        {
            path = From(text);
        }
        catch (ArgumentException)
        {
            path = null;
        }
        catch (PathTooLongException)
        {
            path = null;
        }

        return path is not null;
    }

    /// <summary>
    /// Reads text that must already name an absolute path, such as the project in an address. It
    /// gives false for relative text, which the system would otherwise resolve against the working
    /// directory of the app, and for text that the system refuses as a path.
    /// </summary>
    public static bool TryFromAbsolute(string text, [NotNullWhen(true)] out ProjectPath? path)
    {
        if (!Path.IsPathFullyQualified(text))
        {
            path = null;
            return false;
        }

        return TryFrom(text, out path);
    }

    public bool Equals(ProjectPath? other) => other is not null && PathComparer.Equals(Value, other.Value);

    public override bool Equals(object? other) => Equals(other as ProjectPath);

    public override int GetHashCode() => PathComparer.GetHashCode(Value);

    public override string ToString() => Value;
}

/// <summary>Writes a ProjectPath to the registry file as a plain string.</summary>
public sealed class ProjectPathJsonConverter : JsonConverter<ProjectPath>
{
    public override ProjectPath Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
        ProjectPath.From(reader.GetString() ?? string.Empty);

    public override void Write(Utf8JsonWriter writer, ProjectPath value, JsonSerializerOptions options) =>
        writer.WriteStringValue(value.Value);
}
