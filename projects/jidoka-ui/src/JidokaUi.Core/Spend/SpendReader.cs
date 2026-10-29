using JidokaUi.Core.Boards;
using JidokaUi.Core.Factory;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Spend;

/// <summary>
/// Builds the spend view. The ledger holds the dollars, and the backlog of each project says which
/// tasks merged: a task is merged when its bead is closed and held a lap. A project that bd does not
/// answer for has no merged task here, so the view names it instead of guessing.
/// </summary>
public sealed class SpendReader
{
    private readonly Ledger ledger;
    private readonly ProjectCatalog catalog;
    private readonly BacklogCache backlogs;

    public SpendReader(Ledger ledger, ProjectCatalog catalog, BacklogCache backlogs)
    {
        this.ledger = ledger;
        this.catalog = catalog;
        this.backlogs = backlogs;
    }

    /// <summary>The Monday, in UTC, of the week that holds this moment.</summary>
    public static DateOnly WeekOf(DateTimeOffset moment) => WeekOf(DateOnly.FromDateTime(moment.UtcDateTime));

    /// <summary>The Monday of the week that holds this day.</summary>
    public static DateOnly WeekOf(DateOnly day) =>
        day.AddDays(-(((int)day.DayOfWeek + 6) % 7));

    /// <summary>Reads the ledger and every project of the registry, and builds the view of one week.</summary>
    public async Task<SpendView> ReadAsync(DateOnly week, SpendGrouping by)
    {
        var read = await Task.Run(ledger.Read);
        var known = await Task.WhenAll(catalog.Projects().Select(KnownAsync));

        var reasons = new List<string>();
        if (read.Reason.Length > 0)
        {
            reasons.Add(read.Reason);
        }

        reasons.AddRange(known.Where(project => project.Reason.Length > 0).Select(project => project.Reason));

        var inTheWeek = read.Runs.Where(run => WeekOf(run.At) == week).ToList();
        return new SpendView(
            week,
            by,
            Weeks(read.Runs),
            PerMergedTask(inTheWeek, by, known),
            Epics(inTheWeek, by, known),
            inTheWeek.Count(run => run.Dollars is null),
            reasons);
    }

    private static List<WeekSpend> Weeks(IReadOnlyList<LedgerRun> runs) =>
        [.. runs
            .GroupBy(run => WeekOf(run.At))
            .OrderByDescending(group => group.Key)
            .Select(group => new WeekSpend(group.Key, group.Sum(run => run.Dollars ?? 0m), group.Count()))];

    private static List<GroupCost> PerMergedTask(
        List<LedgerRun> runs,
        SpendGrouping by,
        ProjectKnowledge[] known) =>
        [.. runs
            .Where(run => run.Task is not null && IsMerged(run, known))
            .GroupBy(run => by.ValueOf(run), StringComparer.Ordinal)
            .OrderBy(group => group.Key, StringComparer.Ordinal)
            .Select(group => new GroupCost(
                group.Key,
                group.Sum(run => run.Dollars ?? 0m),
                group.Select(run => (run.Repo, run.Task)).Distinct().Count()))];

    private static List<EpicSpend> Epics(List<LedgerRun> runs, SpendGrouping by, ProjectKnowledge[] known) =>
        [.. runs
            .GroupBy(run => (Project: ProjectOf(run.Repo, known)?.Project, run.Repo, run.Epic))
            .Select(group => new EpicSpend(
                group.Key.Project,
                group.Key.Epic,
                ProjectOf(group.Key.Repo, known)?.TitleOf(group.Key.Epic) ?? group.Key.Epic,
                group.Sum(run => run.Dollars ?? 0m),
                group.Where(run => IsMerged(run, known)).Select(run => run.Task).Distinct().Count(),
                group.Where(run => IsMerged(run, known)).Sum(run => run.Dollars ?? 0m),
                [.. group
                    .GroupBy(run => by.ValueOf(run), StringComparer.Ordinal)
                    .OrderBy(inGroup => inGroup.Key, StringComparer.Ordinal)
                    .Select(inGroup => new GroupSpend(inGroup.Key, inGroup.Sum(run => run.Dollars ?? 0m)))]))
            .OrderByDescending(epic => epic.Dollars)
            .ThenBy(epic => epic.Id, StringComparer.Ordinal)];

    private static bool IsMerged(LedgerRun run, ProjectKnowledge[] known) =>
        run.Task is { } task && ProjectOf(run.Repo, known)?.Merged.Contains(task) == true;

    private static ProjectKnowledge? ProjectOf(string repo, ProjectKnowledge[] known) =>
        ProjectPath.TryFromAbsolute(repo, out var path)
            ? known.FirstOrDefault(project => project.Project.Equals(path))
            : null;

    private async Task<ProjectKnowledge> KnownAsync(ProjectPath project)
    {
        var outcome = await backlogs.ReadAsync(project);
        if (!outcome.Answered)
        {
            return new ProjectKnowledge(project, [], new Dictionary<string, string>(), $"{project.DirectoryName}. {outcome.Message}");
        }

        var beads = outcome.Backlog.Beads;
        var merged = beads
            .Where(bead => !bead.IsEpic && bead.IsClosed && TaskLap.Of(bead).IsMerged)
            .Select(bead => bead.Id)
            .ToHashSet(StringComparer.Ordinal);
        var titles = beads
            .Where(bead => bead.IsEpic && bead.Id.Length > 0 && bead.Title.Length > 0)
            .GroupBy(bead => bead.Id, StringComparer.Ordinal)
            .ToDictionary(group => group.Key, group => group.First().Title, StringComparer.Ordinal);
        return new ProjectKnowledge(project, merged, titles, string.Empty);
    }

    private sealed record ProjectKnowledge(
        ProjectPath Project,
        HashSet<string> Merged,
        Dictionary<string, string> Titles,
        string Reason)
    {
        public string TitleOf(string epic) => Titles.TryGetValue(epic, out var title) ? title : epic;
    }
}
