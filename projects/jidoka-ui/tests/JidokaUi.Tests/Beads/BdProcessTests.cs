using System.Runtime.Versioning;
using JidokaUi.Core.Beads;

namespace JidokaUi.Tests.Beads;

public sealed class BdProcessTests
{
    [Fact]
    public async Task SaysBdIsNotOnThePathWhenNoProgramHasItsName()
    {
        using var directory = new TempDirectory();

        var result = await new BdProcess("jidoka-ui-has-no-such-program")
            .RunAsync(directory.Path, ["ready"], CancellationToken.None);

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

        var result = await new BdProcess(bd).RunAsync(directory.Path, ["ready"], CancellationToken.None);

        Assert.Equal(-1, result.ExitCode);
        Assert.DoesNotContain("is not on the PATH", result.StandardError);
        Assert.Contains("Permission denied", result.StandardError);
    }

    [Fact]
    public async Task SaysBdDidNotStartWhenNothingNamesTheProgramToLaunch()
    {
        using var directory = new TempDirectory();

        var result = await new BdProcess(string.Empty).RunAsync(directory.Path, ["ready"], CancellationToken.None);

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
        await File.WriteAllTextAsync(script, ScriptChild.ScriptThatSleeps(childFile));
        File.SetUnixFileMode(script, UnixFileMode.UserRead | UnixFileMode.UserExecute);
        using var stop = new CancellationTokenSource();

        var run = new BdProcess(script).RunAsync(directory.Path, [], stop.Token);
        var child = await ScriptChild.StartedAsync(childFile);
        await stop.CancelAsync();
        await run.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.True(await ScriptChild.HasEndedAsync(child), $"The child {child} of the stopped script is still running.");
    }
}
