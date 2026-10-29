using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Spend;
using JidokaUi.Tests.Boards;

namespace JidokaUi.Tests.Spend;

public sealed class SpendReaderTests : IDisposable
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string TheEpicAndItsTasks =
        """
        [
          {"id": "b", "title": "The site", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]},
          {"id": "b.1", "title": "Pick a plan", "issue_type": "task", "status": "closed", "parent": "b",
           "metadata": {"lap.number": 1, "lap.stage": "merge"}},
          {"id": "b.2", "title": "Launch", "issue_type": "task", "status": "in_progress", "parent": "b",
           "metadata": {"lap.number": 1, "lap.stage": "build"}},
          {"id": "b.3", "title": "Write the footer", "issue_type": "task", "status": "closed", "parent": "b",
           "metadata": {"lap.number": 1, "lap.stage": "merge"}}
        ]
        """;

    private static readonly DateTimeOffset Monday = new(2026, 10, 19, 9, 0, 0, TimeSpan.Zero);
    private static readonly DateOnly ThisWeek = new(2026, 10, 19);

    private readonly TwoProjects projects = new();

    [Fact]
    public async Task DividesTheDollarsOfEachModelByTheMergedTasksThatRanOnItAndLeavesOutATaskThatHasNotMerged()
    {
        var view = await ReadAsync(SpendGrouping.Model);

        Assert.Equal(
            [("opus", 2.00m, 1, 2.00m), ("sonnet", 2.00m, 2, 1.00m)],
            view.PerMergedTask.Select(group => (group.Group, group.Dollars, group.MergedTasks, group.DollarsPerTask)));
    }

    [Theory]
    [InlineData(SpendGrouping.Tier, "deep $2.00 over 1; standard $2.00 over 2")]
    [InlineData(SpendGrouping.Effort, "high $3.50 over 2; medium $0.50 over 1")]
    [InlineData(SpendGrouping.Track, "full $3.50 over 1; simple $0.50 over 1")]
    public async Task GroupsTheCostOfAMergedTaskByTierEffortOrTrack(SpendGrouping by, string expected)
    {
        var view = await ReadAsync(by);

        Assert.Equal(
            expected,
            string.Join(
                "; ",
                view.PerMergedTask.Select(group => FormattableString.Invariant(
                    $"{group.Group} ${group.Dollars:F2} over {group.MergedTasks}"))));
    }

    [Fact]
    public async Task SumsEachEpicOfTheWeekAndBreaksItDownByTheGrouping()
    {
        var view = await ReadAsync(SpendGrouping.Model);

        var epic = Assert.Single(view.Epics);
        Assert.Equal(("The site", projects.Second, 8.25m), (epic.Title, epic.Project, epic.Dollars));
        Assert.Equal(
            [("opus", 2.25m), ("sonnet", 6.00m)],
            epic.Breakdown.Select(group => (group.Group, group.Dollars)));
    }

    [Fact]
    public async Task DividesTheDollarsOfTheMergedTasksOfAnEpicByTheirNumber()
    {
        var view = await ReadAsync(SpendGrouping.Model);

        var epic = Assert.Single(view.Epics);
        Assert.Equal((2, 2.00m), (epic.MergedTasks, epic.DollarsPerMergedTask));
    }

    [Fact]
    public async Task NamesTheWeeksThatHoldARunNewestFirstWithTheDollarsOfEach()
    {
        var view = await ReadAsync(SpendGrouping.Model);

        Assert.Equal(
            [(new DateOnly(2026, 10, 19), 8.25m), (new DateOnly(2026, 10, 12), 3.00m)],
            view.Weeks.Select(week => (week.Start, week.Dollars)));
    }

    [Fact]
    public async Task ShowsOnlyTheRunsOfTheWeekThatWasAskedFor()
    {
        var view = await TheReader(answers: true).ReadAsync(new DateOnly(2026, 10, 12), SpendGrouping.Model);

        Assert.Equal([("The site", 3.00m)], view.Epics.Select(epic => (epic.Title, epic.Dollars)));
    }

    [Fact]
    public async Task CountsARunWithNoPriceAndAddsNoDollarsForIt()
    {
        var reader = TheReader(answers: true);
        new FakeLedger(projects.JidokaHome)
            .Ran(new LedgerRun(Monday, projects.Second.Value, "b", "b.1", "build", "full", "standard", "mystery", "high", null));

        var view = await reader.ReadAsync(ThisWeek, SpendGrouping.Model);

        Assert.Equal(1, view.UnpricedRuns);
        Assert.Equal(8.25m, Assert.Single(view.Epics).Dollars);
    }

    [Fact]
    public async Task NamesAProjectThatBdDidNotAnswerForAndStillShowsTheSpend()
    {
        projects.Bd.Fails(ListCommand, "no beads here");

        var view = await TheReader(answers: false).ReadAsync(ThisWeek, SpendGrouping.Model);

        Assert.Empty(view.PerMergedTask);
        Assert.Contains(view.Reasons, reason => reason.Contains("second", StringComparison.Ordinal));
        Assert.Equal(8.25m, Assert.Single(view.Epics).Dollars);
    }

    private Task<SpendView> ReadAsync(SpendGrouping by) => TheReader(answers: true).ReadAsync(ThisWeek, by);

    private SpendReader TheReader(bool answers)
    {
        if (answers)
        {
            projects.Bd
                .PrintsIn(projects.First.Value, ListCommand, "[]")
                .PrintsIn(projects.Second.Value, ListCommand, TheEpicAndItsTasks);
        }

        new FakeLedger(projects.JidokaHome)
            .Ran(new LedgerRun(Monday, projects.Second.Value, "b", "b.1", "research", "full", "deep", "opus", "high", 2.00m))
            .Ran(new LedgerRun(Monday, projects.Second.Value, "b", "b.1", "build", "full", "standard", "sonnet", "high", 1.00m))
            .Ran(new LedgerRun(Monday, projects.Second.Value, "b", "b.1", "spec-check", "full", "standard", "sonnet", "medium", 0.50m))
            .Ran(new LedgerRun(Monday, projects.Second.Value, "b", "b.2", "build", "full", "standard", "sonnet", "high", 4.00m))
            .Ran(new LedgerRun(Monday, projects.Second.Value, "b", "b.3", "build", "simple", "standard", "sonnet", "high", 0.50m))
            .Ran(new LedgerRun(Monday, projects.Second.Value, "b", null, "manager", null, null, "opus", null, 0.25m))
            .Ran(new LedgerRun(Monday.AddDays(-7), projects.Second.Value, "b", "b.0", "build", "simple", "standard", "sonnet", "high", 3.00m));
        return new SpendReader(new Ledger(new JidokaHome(projects.JidokaHome)), projects.Catalog, projects.Backlogs);
    }

    public void Dispose() => projects.Dispose();
}
