using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The address of the doctor page. It names the project whose bd the page reports, so a reload of
/// the page reports the same bd whichever project another tab switched to.
/// </summary>
public static class DoctorAddress
{
    /// <summary>The page that every doctor address names.</summary>
    public const string Page = "doctor";

    /// <summary>
    /// The address of the doctor page that names this project. With no project, it is the doctor
    /// address that names none.
    /// </summary>
    public static string Of(ProjectPath? project) =>
        project is null
            ? Page
            : $"{Page}?{ProjectInTheAddress.QueryName}={Uri.EscapeDataString(project.Value)}";
}
