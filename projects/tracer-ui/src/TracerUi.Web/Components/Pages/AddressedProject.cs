using TracerUi.Core.Projects;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// The project that a page showing one project reads, or the reason it reads none. The address
/// names the project and wins over the tab's, and that project can be one the registry no longer
/// holds. An address that names none reads the project of the tab, and when the tab has none either,
/// the page reads nothing.
/// </summary>
public abstract record AddressedProject
{
    // Closes the hierarchy: without it another assembly could add a fourth case, and every page
    // that tests for Found, Lost and Unnamed alone would fall through it and draw nothing.
    private AddressedProject()
    {
    }

    /// <summary>The project that this page reads.</summary>
    public sealed record Found(ProjectPath Project) : AddressedProject;

    /// <summary>Why this page reads no project, in the words that it shows a person.</summary>
    public sealed record Lost(string Reason) : AddressedProject;

    /// <summary>Neither the address nor the tab names a project, so this page has none to read.</summary>
    public sealed record Unnamed : AddressedProject;
}
