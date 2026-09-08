namespace TracerUi.Tests;

/// <summary>
/// A fact that only Windows can prove, because it uses a Windows drive letter.
/// Other systems have no such letter, so they skip the fact.
/// </summary>
public sealed class WindowsFactAttribute : FactAttribute
{
    public WindowsFactAttribute()
    {
        if (!OperatingSystem.IsWindows())
        {
            Skip = "The test needs a Windows drive letter, which this system does not have.";
        }
    }
}
