using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Spend;

/// <summary>One week of the ledger. A week starts on a Monday, in UTC.</summary>
public sealed record WeekSpend(DateOnly Start, decimal Dollars, int Runs);

/// <summary>The dollars of the runs that have one value in the grouped column.</summary>
public sealed record GroupSpend(string Group, decimal Dollars);

/// <summary>
/// What the merged tasks that ran on one value of the grouped column cost. A task counts once in each
/// group it ran in, with the dollars of its runs in that group.
/// </summary>
public sealed record GroupCost(string Group, decimal Dollars, int MergedTasks)
{
    public decimal DollarsPerTask => Dollars / MergedTasks;
}

/// <summary>
/// One epic's spend in the week, with every run that belongs to it: the runs of its tasks, of its
/// pass and the requests of its manager.
/// </summary>
/// <param name="Project">The project of the registry that holds the epic, or null when the registry holds none at that path.</param>
/// <param name="Title">The title of the epic, or its id when no backlog names it.</param>
/// <param name="MergedTasks">The merged tasks of the epic that have a run in the week.</param>
/// <param name="MergedDollars">The dollars of the runs of those tasks, which leave out the pass and the manager.</param>
public sealed record EpicSpend(
    ProjectPath? Project,
    string Id,
    string Title,
    decimal Dollars,
    int MergedTasks,
    decimal MergedDollars,
    IReadOnlyList<GroupSpend> Breakdown)
{
    /// <summary>The cost per merged task of the epic, or null when no task of it merged in the week.</summary>
    public decimal? DollarsPerMergedTask => MergedTasks == 0 ? null : MergedDollars / MergedTasks;
}

/// <summary>The spend view of one week, grouped by one column of the ledger.</summary>
/// <param name="Weeks">Every week that holds a run, newest first.</param>
/// <param name="PerMergedTask">The cost per merged task of the week, by value of the grouped column.</param>
/// <param name="UnpricedRuns">The runs of the week whose model had no listed price, which add no dollars.</param>
/// <param name="Reasons">Why part of the view is missing, such as a ledger or a project that did not answer.</param>
public sealed record SpendView(
    DateOnly Week,
    SpendGrouping By,
    IReadOnlyList<WeekSpend> Weeks,
    IReadOnlyList<GroupCost> PerMergedTask,
    IReadOnlyList<EpicSpend> Epics,
    int UnpricedRuns,
    IReadOnlyList<string> Reasons);
