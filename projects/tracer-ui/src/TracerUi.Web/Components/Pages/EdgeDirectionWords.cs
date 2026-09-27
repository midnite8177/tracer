namespace TracerUi.Web.Components.Pages;

/// <summary>
/// The words of one direction of the dependencies: what the list is called, what it says when no
/// bead belongs in it, and what a cut of it does, because each direction cuts a different edge.
/// </summary>
public sealed record EdgeDirectionWords(string Title, string WhenEmpty, string CutTitle);
