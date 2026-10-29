using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;

namespace JidokaUi.Core.Jidoka;

/// <summary>
/// The address of a jidoka page, which sits beside the address of its bead. It names the kind of
/// page, the id of the bead and the project that holds the bead, because an id alone means nothing
/// outside its project.
/// </summary>
public static class ServedPageAddress
{
    /// <summary>The first segment of every address of a jidoka page.</summary>
    public const string Root = "jidoka-page";

    /// <summary>The path below which the pages of one kind sit, one for each bead id.</summary>
    public static string DirectoryOf(JidokaPageKind kind) => $"{Root}/{kind.Word()}";

    /// <summary>The address of the page of this kind beside this bead.</summary>
    public static string Of(JidokaPageKind kind, BeadAddress bead) =>
        $"{DirectoryOf(kind)}/{Uri.EscapeDataString(bead.Id)}?{ProjectInTheAddress.QueryName}={Uri.EscapeDataString(bead.Project.Value)}";
}
