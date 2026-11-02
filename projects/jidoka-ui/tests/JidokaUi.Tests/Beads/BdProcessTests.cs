using System.Diagnostics;
using System.Runtime.Versioning;
using JidokaUi.Core.Beads;

namespace JidokaUi.Tests.Beads;

public sealed class BdProcessTests
{
    [Fact]
    public async Task SaysBdIsNotOnThePathWhenNoProgramHasItsName()
    {
        using var directory = new TempDirectory();

        var result = await new BdProcess("jidoka-ui-has-no-such-program").RunAsync(directory.Path, ["ready"]);

        Assert.Equal(-1, result.ExitCode);
        Assert.Contains("is not on the PATH", result.StandardError);
    }

    [UnixFact]
    [UnsupportedOSPlatform("windows")]
    public async Task NamesWhatFailedWhenBdExistsAndCannotRun()
    {
        using var directory = new TempDirectory();
        var bd = Path.Combine(directory.Path, "bd");
        await File.WriteAllTextAsync(bd, "#!/bin/sh\n");
        File.SetUnixFileMode(bd, UnixFileMode.UserRead);

        var result = await new BdProcess(bd).RunAsync(directory.Path, ["ready"]);

        Assert.Equal(-1, result.ExitCode);
        Assert.DoesNotContain("is not on the PATH", result.StandardError);
        Assert.Contains("Permission denied", result.StandardError);
    }

    [Fact]
    public async Task SaysBdDidNotStartWhenNothingNamesTheProgramToLaunch()
    {
        using var directory = new TempDirectory();

        var result = await new BdProcess(string.Empty).RunAsync(directory.Path, ["ready"]);

        Assert.Equal(-1, result.ExitCode);
        Assert.Contains("did not start", result.StandardError);
    }

    [UnixFact]
    [UnsupportedOSPlatform("windows")]
    public async Task KillsTheProgramAndTheProcessesItStartedWhenTheRunIsStopped()
    {
        using var directory = new TempDirectory();
        var script = Path.Combine(directory.Path, "never-ends");
        var childFile = Path.Combine(directory.Path, "child.pid");
        await File.WriteAllTextAsync(script, $"#!/bin/sh\nsleep 300 &\necho $! > '{childFile}'\nwait\n");
        File.SetUnixFileMode(script, UnixFileMode.UserRead | UnixFileMode.UserExecute);
        using var stop = new CancellationTokenSource();

        var run = new BdProcess(script).RunAsync(directory.Path, [], stop.Token);
        var child = await TheChildThatTheScriptStarted(childFile);
        await stop.CancelAsync();
        await run.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.True(await HasEnded(child), $"The child {child} of the stopped script is still running.");
    }

    private static async Task<int> TheChildThatTheScriptStarted(string childFile)
    {
        var deadline = DateTime.UtcNow.AddSeconds(10);
        while (DateTime.UtcNow < deadline)
        {
            if (File.Exists(childFile) && int.TryParse(await File.ReadAllTextAsync(childFile), out var pid))
            {
                return pid;
            }

            await Task.Delay(20);
        }

        throw new TimeoutException("The script did not start its child.");
    }

    private static async Task<bool> HasEnded(int pid)
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
