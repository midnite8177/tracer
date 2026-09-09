namespace TracerUi.Web.Components.Pages;

/// <summary>
/// Whether one direction of the dependencies can cut an edge right now: whether the installed bd
/// offers the write, what the tooltip says when it cannot, and whether a cut that this list started
/// is still writing.
/// </summary>
public sealed record CutCapability(bool Cuttable, string WhyNot, bool Writing);
