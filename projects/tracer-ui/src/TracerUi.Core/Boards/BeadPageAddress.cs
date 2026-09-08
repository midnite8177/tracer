using TracerUi.Core.Beads;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The address of the detail page of one bead. It names the project that holds the bead, because an
/// id alone means nothing outside its project. A tab that the browser opens beside this one carries
/// no active project of its own, so the address is where that tab learns which project to read.
/// </summary>
public static class BeadPageAddress
{
    /// <summary>The page that every bead address names.</summary>
    public const string Page = "bead";

    private const string Project = "project";

    /// <summary>
    /// The address of the detail page of a bead of the active project. It names no project, so the
    /// tab that opens it reads the project that the browser holds.
    /// </summary>
    public static string Of(string id) => $"{Page}/{Uri.EscapeDataString(id)}";

    /// <summary>The address of the detail page of this bead, which names the project that holds it.</summary>
    public static string Of(BeadAddress bead) =>
        $"{Of(bead.Id)}?{Project}={Uri.EscapeDataString(bead.Project.Value)}";

    /// <summary>
    /// The project that this address names, or null when it names none and when it names text that
    /// is no path. A tab at such an address keeps the project that the browser holds.
    /// </summary>
    public static ProjectPath? ProjectIn(string address) =>
        ProjectPath.TryFrom(AddressQuery.Of(address).GetValueOrDefault(Project, string.Empty), out var project)
            ? project
            : null;
}
