using Microsoft.AspNetCore.Components;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// The project that a page showing one project reads, as its address names it, and the rule that
/// makes that project the active project of the tab. Every such page builds one, so an address that
/// names a project, one that names none, and one whose project the registry no longer holds mean
/// the same on each. A take of an address that leads to the page makes its project the active one,
/// and replaces an address that names none with the address that names the project the page reads.
/// The replace hands the page its parameters again, during the take or after it, and the take that
/// this starts gives <see cref="AddressChange.Same"/>.
/// </summary>
public sealed class PageProject
{
    private readonly NavigationManager navigation;
    private readonly ActiveProjectSelection selection;
    private readonly string page;
    private readonly string whatThePageShows;
    private readonly Func<ProjectPath, string> theAddressOf;
    private bool addressTaken;

    /// <summary>The project of one page, which builds the addresses of that page alone.</summary>
    /// <param name="navigation">The navigation of the page, which holds its current address.</param>
    /// <param name="selection">The active project of the tab.</param>
    /// <param name="page">The path that every address of the page starts with, such as "board".</param>
    /// <param name="whatThePageShows">
    /// The end of the sentence that says why the page reads no project, such as "that holds this bead".
    /// </param>
    /// <param name="theAddressOf">The address of this page that names the project it is given.</param>
    public PageProject(
        NavigationManager navigation,
        ActiveProjectSelection selection,
        string page,
        string whatThePageShows,
        Func<ProjectPath, string> theAddressOf)
    {
        this.navigation = navigation;
        this.selection = selection;
        this.page = page;
        this.whatThePageShows = whatThePageShows;
        this.theAddressOf = theAddressOf;
    }

    /// <summary>The project that the page reads, or why it reads none.</summary>
    public AddressedProject Addressed { get; private set; } = new AddressedProject.Unnamed();

    /// <summary>The project that the page reads, or null while it reads none.</summary>
    public ProjectPath? OnTheScreen =>
        Addressed is AddressedProject.Found { Project: var project } ? project : null;

    /// <summary>
    /// Whether the page reads this project now. An answer that bd gives after the page left the
    /// project it was asked for stays off the screen when this is false.
    /// </summary>
    public bool Shows(ProjectPath project) => project.Equals(OnTheScreen);

    /// <summary>Takes the address of a page with no id below it, such as the board.</summary>
    public AddressChange TakeTheAddress() =>
        LeadsHere(navigation.Uri) ? Take() : new AddressChange.Elsewhere();

    /// <summary>
    /// Takes the address of the page of one id below the page, such as the page of one bead. The
    /// change says what happened to the project alone; the page compares the id itself.
    /// </summary>
    /// <param name="id">The id that the router handed the page.</param>
    public AddressChange TakeTheAddressOf(string id) =>
        LeadsHereFor(navigation.Uri, id) ? Take() : new AddressChange.Elsewhere();

    private AddressChange Take()
    {
        var before = OnTheScreen;
        var first = !addressTaken;

        // The rewrite below hands the page its parameters again. A take that still found the old
        // state would give the project a second time, and the page would ask bd twice for one address.
        addressTaken = true;
        Addressed = SelectTheProjectOfTheAddress();
        if (OnTheScreen is not { } project)
        {
            return new AddressChange.NoProject();
        }

        AddressChange change = first ? new AddressChange.FirstProject(project)
            : project.Equals(before) ? new AddressChange.Same()
            : new AddressChange.AnotherProject(project);
        NameTheProjectInAnAddressThatNamesNone(project);
        return change;
    }

    // Whether this address leads to the page, whatever its query, fragment, trailing slash or letter
    // case.
    private bool LeadsHere(string address) =>
        string.Equals(ThePathOf(address), page, StringComparison.OrdinalIgnoreCase);

    // Whether this address leads to the page of this one id below the page, whatever its query,
    // fragment or trailing slash. The page matches in any letter case. The id matches in exact letter
    // case after one unescape, as the router hands it to the page.
    private bool LeadsHereFor(string address, string id)
    {
        var path = ThePathOf(address);
        var below = $"{page}/";
        return path.StartsWith(below, StringComparison.OrdinalIgnoreCase)
            && string.Equals(Uri.UnescapeDataString(path[below.Length..]), id, StringComparison.Ordinal);
    }

    private string ThePathOf(string address) =>
        navigation.ToBaseRelativePath(address).Split('?', '#')[0].TrimEnd('/');

    // Replaces an address that names no project with the address of the same page that names this
    // one, so a link copied from the address bar names its project. The replace keeps the history as
    // it was, so Back skips the address that named none. An address that names something stays, so
    // a page whose project left the registry keeps saying so.
    private void NameTheProjectInAnAddressThatNamesNone(ProjectPath project)
    {
        if (ProjectInTheAddress.Of(navigation.Uri) is ProjectInTheAddress.None)
        {
            navigation.NavigateTo(theAddressOf(project), replace: true);
        }
    }

    // An address that names none reads the active project of the tab, or Unnamed when the tab has
    // none. An address whose project the page cannot read gives the reason, and never the project of
    // the tab.
    private AddressedProject SelectTheProjectOfTheAddress()
    {
        switch (ProjectInTheAddress.Of(navigation.Uri))
        {
            case ProjectInTheAddress.Named { Project: var project }:
                return selection.Select(project)
                    ? new AddressedProject.Found(project)
                    : new AddressedProject.Lost(
                        $"{project.DirectoryName} is not in the registry any more, "
                        + $"so this address names no project {whatThePageShows}.");
            case ProjectInTheAddress.NoPath { Text: var text }:
                return new AddressedProject.Lost(
                    $"{text} is no project path, so this address names no project {whatThePageShows}.");
        }

        return selection.Current is { } active
            ? new AddressedProject.Found(active)
            : new AddressedProject.Unnamed();
    }
}
