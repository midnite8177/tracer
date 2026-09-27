using TracerUi.Core.Projects;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// What the address asks of a page that shows one project, each time the page takes it. Blazor
/// hands the page its parameters on every change of the query, including the change that leaves the
/// page before the router drops it, so most changes ask for nothing new.
/// </summary>
public abstract record AddressChange
{
    // Closes the hierarchy, so a page that handles these five cases handles every change.
    private AddressChange()
    {
    }

    /// <summary>
    /// The project whose bd the page has not asked yet, from <see cref="FirstProject"/> or
    /// <see cref="AnotherProject"/>. Null when the address asks for nothing new.
    /// </summary>
    public ProjectPath? ProjectToRead => this switch
    {
        FirstProject { Project: var project } => project,
        AnotherProject { Project: var project } => project,
        _ => null,
    };

    /// <summary>The address leads to another page, and the page leaves what it shows as it is.</summary>
    public sealed record Elsewhere : AddressChange;

    /// <summary>The address names the project that the page shows already. The rest of the address may differ.</summary>
    public sealed record Same : AddressChange;

    /// <summary>The page shows no project, and <see cref="PageProject.Addressed"/> says why.</summary>
    public sealed record NoProject : AddressChange;

    /// <summary>
    /// The project of the first address that the page takes. When that address names no project,
    /// the page gets <see cref="NoProject"/>, and the project of a later address comes as
    /// <see cref="AnotherProject"/>.
    /// </summary>
    public sealed record FirstProject(ProjectPath Project) : AddressChange;

    /// <summary>A project other than the one that the page showed at its address before.</summary>
    public sealed record AnotherProject(ProjectPath Project) : AddressChange;
}
