using System.Diagnostics.CodeAnalysis;

namespace TracerUi.Core.Look;

/// <summary>The light or the dark reading of the app.</summary>
public sealed record Theme
{
    private Theme(string name)
    {
        Name = name;
    }

    public static Theme Light { get; } = new("light");

    public static Theme Dark { get; } = new("dark");

    /// <summary>The key that holds the chosen theme in the storage of one browser.</summary>
    public const string StorageKey = "tracer-ui.theme";

    /// <summary>
    /// The attribute of the document element that carries the theme. Bootstrap reads this name, and
    /// the stylesheets key their dark values to it.
    /// </summary>
    public const string DocumentAttribute = "data-bs-theme";

    /// <summary>The word that names this theme, both in storage and in the document.</summary>
    public string Name { get; }

    /// <summary>The theme that a toggle gives, which is the one that this theme is not.</summary>
    public Theme Other => this == Light ? Dark : Light;

    /// <summary>
    /// The theme that a document carries. A document with no theme, or with a word that neither
    /// theme carries, reads as the light one, so a control that reads the document holds no rule.
    /// </summary>
    public static Theme FromDocument(string? attribute) => TryParse(attribute, out var theme) ? theme : Light;

    /// <summary>Reads a stored word. It gives false for a word that neither theme carries.</summary>
    public static bool TryParse(string? name, [NotNullWhen(true)] out Theme? theme)
    {
        theme = name == Light.Name ? Light : name == Dark.Name ? Dark : null;
        return theme is not null;
    }

    public override string ToString() => Name;
}
