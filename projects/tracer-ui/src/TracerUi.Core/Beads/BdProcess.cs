using System.ComponentModel;
using System.Diagnostics;

namespace TracerUi.Core.Beads;

/// <summary>
/// Launches the program it was given and gives back its exit code, its standard output and its
/// standard error.
/// </summary>
public sealed class BdProcess : IBdProcess
{
    // ENOENT on Unix and ERROR_FILE_NOT_FOUND on Windows, which are both 2.
    private const int NoSuchFile = 2;

    private readonly string programName;

    /// <param name="programName">The name that the app looks for on the PATH, or a path to the program itself.</param>
    public BdProcess(string programName)
    {
        this.programName = programName;
    }

    public async Task<BdResult> RunAsync(string workingDirectory, IReadOnlyList<string> arguments)
    {
        var start = new ProcessStartInfo(programName)
        {
            WorkingDirectory = workingDirectory,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };

        foreach (var argument in arguments)
        {
            start.ArgumentList.Add(argument);
        }

        try
        {
            using var bd = Process.Start(start);
            if (bd is null)
            {
                return new BdResult(-1, string.Empty, $"{programName} did not start, and the system gave no process to wait for.");
            }

            // The reads start before the wait, because a program that fills a pipe buffer blocks
            // until something drains it, and a wait that comes first never does.
            var standardOutput = bd.StandardOutput.ReadToEndAsync();
            var standardError = bd.StandardError.ReadToEndAsync();
            await bd.WaitForExitAsync();
            return new BdResult(bd.ExitCode, await standardOutput, await standardError);
        }
        catch (Win32Exception exception) when (exception.NativeErrorCode == NoSuchFile)
        {
            return new BdResult(-1, string.Empty, $"{programName} is not on the PATH of this machine.");
        }
        catch (Exception exception) when (exception is Win32Exception or InvalidOperationException)
        {
            return new BdResult(-1, string.Empty, $"{programName} did not start. {exception.Message}");
        }
    }
}
