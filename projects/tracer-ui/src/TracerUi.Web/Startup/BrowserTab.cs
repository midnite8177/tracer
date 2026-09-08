using System.Diagnostics;
using System.Runtime.InteropServices;

namespace TracerUi.Web.Startup;

/// <summary>Opens the default browser of the person on the address of the app.</summary>
public sealed class BrowserTab : IStartupBrowser
{
    public void Open(string url)
    {
        var (command, arguments) = CommandFor(url);
        try
        {
            using var process = Process.Start(new ProcessStartInfo(command, arguments) { UseShellExecute = false });
        }
        catch (Exception exception) when (exception is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            Console.WriteLine($"tracer-ui runs at {url}. Open it yourself: {exception.Message}");
        }
    }

    private static (string Command, string Arguments) CommandFor(string url)
    {
        if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
        {
            return ("open", url);
        }

        if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
        {
            return ("cmd", $"/c start {url}");
        }

        return ("xdg-open", url);
    }
}
