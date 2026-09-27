using TracerUi.Core.Beads;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The address of the detail page of one bead. It names the project that holds the bead, because an
/// id alone means nothing outside its project, and a tab learns from the address which project to
/// read. It writes no address that leaves the project out.
/// </summary>
public static class BeadPageAddress
{
    /// <summary>The page that every bead page address names.</summary>
    public const string Page = "bead";

    /// <summary>The address of the detail page of this bead, which names the project that holds it.</summary>
    public static string Of(BeadAddress bead) =>
        $"{Page}/{Uri.EscapeDataString(bead.Id)}?{ProjectInTheAddress.QueryName}={Uri.EscapeDataString(bead.Project.Value)}";
}
