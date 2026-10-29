using AngleSharp.Dom;
using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Spend;
using JidokaUi.Tests.Boards;
using SpendPage = JidokaUi.Web.Components.Pages.Spend;

namespace JidokaUi.Tests.Spend;

/// <summary>
/// The spend view as a browser draws it: the weeks, the cost per merged task under the grouping that
/// the address names, and the breakdown of each epic. The ledger is a file in a temporary folder that
/// stands for jidoka's home.
/// </summary>
public sealed class SpendMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string TheEpicAndItsTasks =
        """
        [
          {"id": "b", "title": "The site", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]},
          {"id": "b.1", "title": "Pick a plan", "issue_type": "task", "status": "closed", "parent": "b",
           "metadata": {"lap.number": 1, "lap.stage": "merge"}},
          {"id": "b.2", "title": "Launch", "issue_type": "task", "status": "in_progress", "parent": "b",
           "metadata": {"lap.number": 1, "lap.stage": "build"}}
        ]
        """;

    // The clock of TwoProjects reads Thursday 2026-01-01, which is in the week of this Monday.
    private static readonly DateTimeOffset TheWeekOfTheClock = new(2025, 12, 29, 9, 0, 0, TimeSpan.Zero);

    private readonly TwoProjects projects = new();

    [Fact]
    public void ShowsTheCostPerMergedTaskGroupedByTheModelThatTheAddressNames()
    {
        var page = TheSpendViewAt("spend?week=2025-12-29&by=model");

        Assert.Equal(
            [("opus", "1", "$2.00", "$2.00"), ("sonnet", "1", "$1.00", "$1.00")],
            page.FindAll("table.spend-per-task tr.spend-group").Select(RowOf));
        Assert.Contains("by model", page.Find("h2").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void GroupsByTierWhenTheAddressNamesNoGroupingAndOpensOnTheWeekOfTheClock()
    {
        var page = TheSpendViewAt("spend");

        Assert.Equal(
            ["deep", "standard"],
            page.FindAll("table.spend-per-task tr.spend-group td.spend-name").Select(cell => cell.TextContent));
        Assert.Equal(
            "spend?week=2025-12-29&by=tier",
            page.Find("nav[aria-label=Week] a[aria-current=page]").GetAttribute("href"));
    }

    [Fact]
    public void ShowsTheTotalOfEachEpicAndItsBreakdownUnderTheLinkToTheEpic()
    {
        var page = TheSpendViewAt("spend?week=2025-12-29&by=model");

        var epic = Assert.Single(page.FindAll("section.spend-epic"));
        Assert.Equal("The site", epic.QuerySelector("h3 a")?.TextContent);
        Assert.Equal($"bead/b?project={Uri.EscapeDataString(projects.Second.Value)}", epic.QuerySelector("h3 a")?.GetAttribute("href"));
        Assert.Equal("$7.00", epic.QuerySelector(".spend-total")?.TextContent);
        Assert.Equal("1 merged task, $3.00 per merged task", epic.QuerySelector(".spend-merged")?.TextContent);
        Assert.Equal(
            [("opus", "$2.00"), ("sonnet", "$5.00")],
            epic.QuerySelectorAll("table.spend-breakdown tr.spend-group")
                .Select(row => (Cell(row, "spend-name"), Cell(row, "spend-dollars"))));
    }

    [Fact]
    public void LinksEveryGroupingAndEveryWeekToTheSameViewWithTheOtherChoice()
    {
        var page = TheSpendViewAt("spend?week=2025-12-29&by=model");

        Assert.Equal(
            [
                "spend?week=2025-12-29&by=tier",
                "spend?week=2025-12-29&by=model",
                "spend?week=2025-12-29&by=effort",
                "spend?week=2025-12-29&by=track",
            ],
            page.FindAll("nav[aria-label='Group by'] a").Select(link => link.GetAttribute("href")));
        Assert.Equal(
            ["spend?week=2025-12-29&by=model", "spend?week=2025-12-22&by=model"],
            page.FindAll("nav[aria-label=Week] a").Select(link => link.GetAttribute("href")));
    }

    [Fact]
    public void ShowsTheWeekThatWasAskedForWhenTheLedgerHoldsNoRunInIt()
    {
        var page = TheSpendViewAt("spend?week=2026-03-02&by=model");

        Assert.Empty(page.FindAll("section.spend-epic"));
        Assert.Contains("holds no run", page.Markup, StringComparison.Ordinal);
        Assert.Equal(
            "spend?week=2026-03-02&by=model",
            page.Find("nav[aria-label=Week] a[aria-current=page]").GetAttribute("href"));
    }

    [Fact]
    public void SaysWhyWhenTheLedgerCannotBeRead()
    {
        File.WriteAllText(Path.Combine(projects.JidokaHome, "ledger.sqlite"), "not a database");
        projects.Bd.PrintsIn(projects.First.Value, ListCommand, "[]").PrintsIn(projects.Second.Value, ListCommand, "[]");
        Register();

        var page = TheReadPage();

        Assert.Contains("ledger", page.Find("p.failure-message").TextContent, StringComparison.Ordinal);
    }

    private static (string Group, string Tasks, string Dollars, string Per) RowOf(IElement row) =>
        (Cell(row, "spend-name"), Cell(row, "spend-tasks"), Cell(row, "spend-dollars"), Cell(row, "spend-per"));

    private static string Cell(IElement row, string cssClass) =>
        row.QuerySelector($"td.{cssClass}")?.TextContent ?? string.Empty;

    private IRenderedComponent<SpendPage> TheSpendViewAt(string address)
    {
        projects.Bd
            .PrintsIn(projects.First.Value, ListCommand, "[]")
            .PrintsIn(projects.Second.Value, ListCommand, TheEpicAndItsTasks);
        new FakeLedger(projects.JidokaHome)
            .Ran(new LedgerRun(TheWeekOfTheClock, projects.Second.Value, "b", "b.1", "research", "full", "deep", "opus", "high", 2.00m))
            .Ran(new LedgerRun(TheWeekOfTheClock, projects.Second.Value, "b", "b.1", "build", "full", "standard", "sonnet", "high", 1.00m))
            .Ran(new LedgerRun(TheWeekOfTheClock, projects.Second.Value, "b", "b.2", "build", "full", "standard", "sonnet", "high", 4.00m))
            .Ran(new LedgerRun(TheWeekOfTheClock.AddDays(-7), projects.Second.Value, "b", "b.0", "build", "full", "standard", "sonnet", "high", 3.00m));
        Register();
        Services.GetRequiredService<NavigationManager>().NavigateTo(address);

        return TheReadPage();
    }

    // The page draws its heading at once and its figures when the ledger and the backlogs have answered.
    private IRenderedComponent<SpendPage> TheReadPage()
    {
        var page = Render<SpendPage>();
        page.WaitForElement("h2");
        return page;
    }

    private void Register()
    {
        projects.RegisterOn(Services);
        Services.AddSingleton(new SpendReader(new Ledger(new JidokaHome(projects.JidokaHome)), projects.Catalog, projects.Backlogs));
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
