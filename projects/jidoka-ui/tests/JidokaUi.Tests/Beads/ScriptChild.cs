using System.Diagnostics;

namespace JidokaUi.Tests.Beads;

/// <summary>
/// Follows the child that a test script starts and records in a file, so that a test tells whether
/// stopping the script also ended the child.
/// </summary>
internal static class ScriptChild
{
    /// <summary>The text of a script that starts a long sleep and writes its process id to the file.</summary>
    public static string ScriptThatSleeps(string pidFile) =>
        $"#!/bin/sh\nsleep 300 &\necho $! > '{pidFile}'\nwait\n";

    public static async Task<int> StartedAsync(string pidFile)
    {
        var deadline = DateTime.UtcNow.AddSeconds(10);
        while (DateTime.UtcNow < deadline)
        {
            if (File.Exists(pidFile) && int.TryParse(await File.ReadAllTextAsync(pidFile), out var pid))
            {
                return pid;
            }

            await Task.Delay(20);
        }

        throw new TimeoutException("The script did not start its child.");
    }

    public static async Task<bool> HasEndedAsync(int pid)
    {
        var deadline = DateTime.UtcNow.AddSeconds(10);
        while (DateTime.UtcNow < deadline)
        {
            try
            {
                using var running = Process.GetProcessById(pid);
                if (running.HasExited)
                {
                    return true;
                }
            }
            catch (ArgumentException)
            {
                return true;
            }

            await Task.Delay(20);
        }

        return false;
    }
}
