using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;
using BoardPage = JidokaUi.Web.Components.Pages.Board;

namespace JidokaUi.Tests.Boards;

/// <summary>The saved filters of the board, as a browser draws them, over a registry that can be busy.</summary>
public sealed class SavedFilterMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string TheBeads =
        """
        [{"id": "s-1", "title": "A task", "issue_type": "task", "priority": 2, "status": "open"}]
        """;

    private const string Busy = "The registry is busy. Try again.";

    private readonly TwoProjects projects = new();

    [Fact]
    public void SaysTheRegistryIsBusyAndOffersNoNewFilterWhenTheSaveFindsTheRegistryBusy()
    {
        var board = TheBoardOfTheFirstProject();
        projects.Store.Busy = true;

        SaveTheFilterAs(board, "Triage");

        Assert.Contains(Busy, board.Markup, StringComparison.Ordinal);
        Assert.DoesNotContain(board.FindAll("button"), button => button.TextContent == "Triage");
    }

    [Fact]
    public void SaysTheRegistryIsBusyAndKeepsTheFilterWhenTheForgetFindsTheRegistryBusy()
    {
        new SavedFilterCatalog(projects.Store).Save(projects.First, "Triage", BoardFilter.NeedsYou);
        var board = TheBoardOfTheFirstProject();
        projects.Store.Busy = true;

        board.Find("button[title='Forget this filter']").Click();

        Assert.Contains(Busy, board.Markup, StringComparison.Ordinal);
        Assert.Contains(board.FindAll("button"), button => button.TextContent == "Triage");
    }

    [Fact]
    public void DropsTheBusyWordsOnceASaveOfTheFilterLands()
    {
        var board = TheBoardOfTheFirstProject();
        projects.Store.Busy = true;
        SaveTheFilterAs(board, "Triage");
        projects.Store.Busy = false;

        SaveTheFilterAs(board, "Triage");

        Assert.DoesNotContain(Busy, board.Markup, StringComparison.Ordinal);
        Assert.Contains(board.FindAll("button"), button => button.TextContent == "Triage");
    }

    private static void SaveTheFilterAs(IRenderedComponent<BoardPage> board, string name)
    {
        board.Find("input.board-filter-name").Input(name);
        board.FindAll("button").Single(button => button.TextContent.Trim() == "Save the filter").Click();
    }

    private IRenderedComponent<BoardPage> TheBoardOfTheFirstProject()
    {
        projects.Bd.PrintsIn(projects.First.Value, ListCommand, TheBeads);
        projects.RegisterOn(Services);
        Services.AddSingleton(new SavedFilterCatalog(projects.Store));
        Services.AddSingleton(new BulkWriter(projects.Adapter));
        Services.GetRequiredService<NavigationManager>()
            .NavigateTo(BoardFilterAddress.Of(projects.First, BoardFilter.Everything));

        var board = Render<BoardPage>();
        board.WaitForAssertion(() => Assert.NotEmpty(board.FindAll("a.board-title")));
        return board;
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
