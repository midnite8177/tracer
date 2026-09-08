using TracerUi.Core.Projects;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// The project that the detail page reads, or the reason it reads none. The address names a project
/// when the tab that opened it carries no active project of its own, and that project can be one the
/// registry no longer holds.
/// </summary>
public abstract record AddressedProject
{
    // Closes the hierarchy: without it another assembly could add a third case, and every page
    // that tests for Found and Lost alone would fall through it and draw nothing.
    private AddressedProject()
    {
    }

    /// <summary>The project that this page reads.</summary>
    public sealed record Found(ProjectPath Project) : AddressedProject;

    /// <summary>Why this page reads no project, in the words that it shows a person.</summary>
    public sealed record Lost(string Reason) : AddressedProject;
}
