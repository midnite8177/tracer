using TracerUi.Core.Beads;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// Where a press on a bead of the needs-you view leads. The address names the project of that bead,
/// so the page that opens reads the bead from the right repository, in this tab and in a new one
/// alike. A project that left the registry between the read and the press leads nowhere, because
/// the detail page would otherwise show a bead of the project that was active before.
/// </summary>
/// <param name="Path">The page to go to, or an empty string when the press leads nowhere.</param>
/// <param name="Message">Empty when the press leads to the bead; otherwise a message for the person.</param>
public sealed record BeadDestination(string Path, string Message)
{
    public bool Reaches => Path.Length > 0;

    public static BeadDestination Of(ProjectCatalog catalog, BeadAddress bead) =>
        catalog.Find(bead.Project) is not null
            ? new BeadDestination(BeadPageAddress.Of(bead), string.Empty)
            : new BeadDestination(
                string.Empty,
                $"{bead.Project.DirectoryName} is not in the registry any more.");
}
