namespace TracerUi.Tests;

/// <summary>
/// A fact that only a non-Windows system can prove, such as one that uses a
/// Unix file mode or that assumes a single filesystem root. Windows skips
/// the fact.
/// </summary>
public sealed class UnixFactAttribute : FactAttribute
{
    public UnixFactAttribute()
    {
        if (OperatingSystem.IsWindows())
        {
            Skip = "The test needs a Unix file mode, which Windows does not have.";
        }
    }
}
