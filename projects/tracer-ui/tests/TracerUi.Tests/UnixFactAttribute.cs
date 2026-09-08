namespace TracerUi.Tests;

/// <summary>
/// A fact that only a Unix system can prove, because it uses a Unix file mode.
/// Windows has no such mode, so Windows skips the fact.
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
