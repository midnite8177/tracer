using System.Runtime.Versioning;
using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class JournalCheckedWriteReportsTests
{
    private static readonly DateTimeOffset Start = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);

    private static readonly TimeSpan Interval = TimeSpan.FromSeconds(1);

    [Fact]
    public void ReportsAWriteThatGrowsTheJournalAtTheNextCheck()
    {
        using var beads = new TempDirectory();
        var journal = AJournalUnder(beads.Path);
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(new FakeWriteReports(), clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        File.AppendAllText(journal, "a write of bd");
        clock.Advance(Interval);

        Assert.Equal(1, writes);
    }

    [Fact]
    public void ReportsNothingWhenAReadOfBdRewritesOnlyTheModifiedTimeOfTheJournal()
    {
        using var beads = new TempDirectory();
        var journal = AJournalUnder(beads.Path);
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(new FakeWriteReports(), clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        File.SetLastWriteTimeUtc(journal, File.GetLastWriteTimeUtc(journal) + TimeSpan.FromMinutes(1));
        clock.Advance(Interval);

        Assert.Equal(0, writes);
    }

    [Fact]
    public void ReportsAWriteWhenAJournalAppearsInABeadsDirectoryThatHadNone()
    {
        using var beads = new TempDirectory();
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(new FakeWriteReports(), clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        clock.Advance(Interval);
        var before = writes;
        AJournalUnder(beads.Path);
        clock.Advance(Interval);

        Assert.Equal((0, 1), (before, writes));
    }

    [Fact]
    public void ReportsAWriteWhenTheJournalGoesAway()
    {
        using var beads = new TempDirectory();
        AJournalUnder(beads.Path);
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(new FakeWriteReports(), clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        Directory.Delete(Path.Combine(beads.Path, "embeddeddolt"), recursive: true);
        clock.Advance(Interval);

        Assert.Equal(1, writes);
    }

    [Fact]
    public void PassesOnTheReportsOfTheWatchWhereBeadsHoldsNoJournal()
    {
        using var beads = new TempDirectory();
        var reports = new FakeWriteReports();
        var clock = new FakeTimeProvider(Start);
        var writes = 0;
        var losses = 0;

        using var watch = new JournalCheckedWriteReports(reports, clock, Interval)
            .Start(beads.Path, () => writes++, () => losses++);
        reports.ReportWrite(beads.Path);
        reports.LoseReports(beads.Path);

        Assert.Equal((1, 1), (writes, losses));
    }

    [Fact]
    public void ReportsOnceAWriteThatTheWatchReportedBeforeTheCheck()
    {
        using var beads = new TempDirectory();
        var journal = AJournalUnder(beads.Path);
        var reports = new FakeWriteReports();
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(reports, clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        File.AppendAllText(journal, "a write of bd");
        reports.ReportWrite(beads.Path);
        clock.Advance(Interval);

        Assert.Equal(1, writes);
    }

    [Fact]
    public void ReportsNothingWhenTheWatchReportsOverAJournalThatDidNotChangeSize()
    {
        using var beads = new TempDirectory();
        var journal = AJournalUnder(beads.Path);
        var reports = new FakeWriteReports();
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(reports, clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        File.SetLastWriteTimeUtc(journal, File.GetLastWriteTimeUtc(journal) + TimeSpan.FromMinutes(1));
        reports.ReportWrite(beads.Path);
        clock.Advance(Interval);

        Assert.Equal(0, writes);
    }

    [Fact]
    public void ReportsAtOnceAWriteThatTheWatchReportsAfterTheJournalGrew()
    {
        using var beads = new TempDirectory();
        var journal = AJournalUnder(beads.Path);
        var reports = new FakeWriteReports();
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(reports, clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        File.AppendAllText(journal, "a write of bd");
        reports.ReportWrite(beads.Path);

        Assert.Equal(1, writes);
    }

    [UnixFact]
    [UnsupportedOSPlatform("windows")]
    public void ReportsAWriteThatTheWatchReportedWhileTheDatabasesCouldNotBeReadAtTheNextCheck()
    {
        using var beads = new TempDirectory();
        var journal = AJournalUnder(beads.Path);
        var databases = Path.Combine(beads.Path, "embeddeddolt");
        var reports = new FakeWriteReports();
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(reports, clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        File.AppendAllText(journal, "a write of bd");
        File.SetUnixFileMode(databases, UnixFileMode.None);
        try
        {
            reports.ReportWrite(beads.Path);
        }
        finally
        {
            File.SetUnixFileMode(databases, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }

        var whileUnreadable = writes;
        clock.Advance(Interval);

        Assert.Equal((0, 1), (whileUnreadable, writes));
    }

    [UnixFact]
    [UnsupportedOSPlatform("windows")]
    public void ReportsNothingWhileTheDatabasesCannotBeRead()
    {
        using var beads = new TempDirectory();
        AJournalUnder(beads.Path);
        var databases = Path.Combine(beads.Path, "embeddeddolt");
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        using var watch = new JournalCheckedWriteReports(new FakeWriteReports(), clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        File.SetUnixFileMode(databases, UnixFileMode.None);
        try
        {
            clock.Advance(Interval);
        }
        finally
        {
            File.SetUnixFileMode(databases, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }

        clock.Advance(Interval);

        Assert.Equal(0, writes);
    }

    [Fact]
    public void StopsBothTheCheckAndTheWatchWhenDisposed()
    {
        using var beads = new TempDirectory();
        var journal = AJournalUnder(beads.Path);
        var reports = new FakeWriteReports();
        var clock = new FakeTimeProvider(Start);
        var writes = 0;

        var watch = new JournalCheckedWriteReports(reports, clock, Interval)
            .Start(beads.Path, () => writes++, () => { });
        watch.Dispose();
        File.AppendAllText(journal, "a write of bd");
        clock.Advance(Interval);
        reports.ReportWrite(beads.Path);

        Assert.Equal(0, writes);
    }

    private static string AJournalUnder(string beads)
    {
        var noms = Path.Combine(beads, "embeddeddolt", "a-database", ".dolt", "noms");
        Directory.CreateDirectory(noms);
        var journal = Path.Combine(noms, JournalCheckedWriteReports.JournalFileName);
        File.WriteAllText(journal, "the first chunks");
        return journal;
    }
}
