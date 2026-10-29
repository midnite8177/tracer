using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Spend;

namespace JidokaUi.Tests.Spend;

public sealed class LedgerTests : IDisposable
{
    private static readonly DateTimeOffset Monday = new(2026, 10, 19, 9, 0, 0, TimeSpan.Zero);

    private readonly TempDirectory home = new();

    [Fact]
    public void ReadsEachRowOfTheFileThatJidokaWrote()
    {
        new FakeLedger(home.Path)
            .Ran(new LedgerRun(Monday, "/work/site", "site-1", "site-1.1", "build", "simple", "standard", "sonnet", "high", 1.25m))
            .Ran(new LedgerRun(Monday.AddHours(1), "/work/site", "site-1", null, "manager", null, null, "opus", null, null));

        var read = new Ledger(new JidokaHome(home.Path)).Read();

        Assert.Equal(string.Empty, read.Reason);
        Assert.Equal(
            [
                new LedgerRun(Monday, "/work/site", "site-1", "site-1.1", "build", "simple", "standard", "sonnet", "high", 1.25m),
                new LedgerRun(Monday.AddHours(1), "/work/site", "site-1", null, "manager", null, null, "opus", null, null),
            ],
            read.Runs);
    }

    [Fact]
    public void ReadsNoRowAndCreatesNoFileWhenJidokaHasWrittenNoLedgerYet()
    {
        var read = new Ledger(new JidokaHome(home.Path)).Read();

        Assert.Empty(read.Runs);
        Assert.Equal(string.Empty, read.Reason);
        Assert.Empty(Directory.GetFileSystemEntries(home.Path));
    }

    [Fact]
    public void LeavesTheFileAndTheFolderAroundItAsTheyWereWhenItReadsThem()
    {
        var ledger = new FakeLedger(home.Path)
            .Ran(new LedgerRun(Monday, "/work/site", "site-1", "site-1.1", "build", "simple", "standard", "sonnet", "high", 1.25m));
        var before = System.IO.File.ReadAllBytes(ledger.File);

        new Ledger(new JidokaHome(home.Path)).Read();

        Assert.Equal(before, System.IO.File.ReadAllBytes(ledger.File));
        Assert.Equal([ledger.File], Directory.GetFileSystemEntries(home.Path));
    }

    public void Dispose() => home.Dispose();
}
