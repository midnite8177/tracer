using System.Runtime.Versioning;
using TracerUi.Core.Beads;

namespace TracerUi.Tests.Beads;

public sealed class BdProcessTests
{
    [Fact]
    public async Task SaysBdIsNotOnThePathWhenNoProgramHasItsName()
    {
        using var directory = new TempDirectory();

        var result = await new BdProcess("tracer-ui-has-no-such-program").RunAsync(directory.Path, ["ready"]);

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
}
