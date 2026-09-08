namespace TracerUi.Core.Look;

/// <summary>
/// The one call that opens a page beside this one, for a caller whose element the browser will not
/// open on its own.
/// </summary>
public static class NewTabCall
{
    /// <summary>The object on the window that holds the call.</summary>
    public const string Holder = "tracerTabs";

    /// <summary>The function of that object which opens the tab and says whether the browser did.</summary>
    public const string Open = "open";

    /// <summary>The name that a caller passes to the browser.</summary>
    public const string Name = $"{Holder}.{Open}";
}
