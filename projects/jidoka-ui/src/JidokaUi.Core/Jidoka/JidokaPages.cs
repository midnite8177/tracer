using JidokaUi.Core.Beads;

namespace JidokaUi.Core.Jidoka;

/// <summary>One jidoka page, as its script wrote it.</summary>
/// <param name="Kind">Which kind of page this is.</param>
/// <param name="Bead">The bead that the page sits beside.</param>
/// <param name="Html">The whole HTML file of the page.</param>
public sealed record JidokaPage(JidokaPageKind Kind, BeadAddress Bead, string Html);

/// <summary>
/// The pages that jidoka's scripts write under its home, one HTML file for each bead and kind, in the
/// folder named for the repository that holds the bead. The app only reads them. A page that cannot
/// be read is a page that is not there, because the bead keeps the record either way.
/// </summary>
public sealed class JidokaPages
{
    private const string Extension = ".html";

    private readonly JidokaHome home;

    /// <param name="home">The home that holds jidoka's pages folder, as <see cref="JidokaHome"/> finds it.</param>
    public JidokaPages(JidokaHome home)
    {
        this.home = home;
    }

    /// <summary>The kinds of page that sit beside this bead, in the order of <see cref="JidokaPageKind"/>.</summary>
    public IReadOnlyList<JidokaPageKind> KindsBeside(BeadAddress bead) =>
        [.. Enum.GetValues<JidokaPageKind>().Where(kind => NameOf(kind, bead, Extension) is { } path && File.Exists(path))];

    /// <summary>The page of this kind beside this bead, or null when there is none or it cannot be read.</summary>
    public JidokaPage? Read(JidokaPageKind kind, BeadAddress bead) =>
        ReadTextOrNull(NameOf(kind, bead, Extension)) is { } html ? new JidokaPage(kind, bead, html) : null;

    /// <summary>
    /// The commit message that the gate script saved beside the gate page of this epic, as the file holds
    /// it, or null when none is saved or the file cannot be read.
    /// </summary>
    public string? SavedGateMessage(BeadAddress epic) =>
        ReadTextOrNull(NameOf(JidokaPageKind.Gate, epic, "-message.txt"));

    // A file that is missing is an IOException too, so one catch covers a file that is not there and
    // one that cannot be read.
    private static string? ReadTextOrNull(string? path)
    {
        if (path is null)
        {
            return null;
        }

        try
        {
            return File.ReadAllText(path);
        }
        catch (IOException)
        {
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            return null;
        }
    }

    private string? NameOf(JidokaPageKind kind, BeadAddress bead, string ending)
    {
        if (!IsAFileName(bead.Id))
        {
            return null;
        }

        return Path.Combine(home.PagesFolder, bead.Project.DirectoryName, $"{kind.Word()}-{bead.Id}{ending}");
    }

    private static bool IsAFileName(string id) =>
        id.Length > 0
        && id != "."
        && id != ".."
        && id.IndexOfAny(['/', '\\', '\0']) < 0
        && id.IndexOfAny(Path.GetInvalidFileNameChars()) < 0;
}
