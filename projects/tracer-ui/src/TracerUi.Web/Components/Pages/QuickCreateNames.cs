namespace TracerUi.Web.Components.Pages;

/// <summary>
/// How one surface names the fields of its quick create: the stem that the id of each control grows
/// from, the words above the title box, and the words that stand in it while it is empty. The two
/// surfaces differ in these three and in nothing else, so they travel together.
/// </summary>
public sealed record QuickCreateNames(string IdPrefix, string Label, string Placeholder);
