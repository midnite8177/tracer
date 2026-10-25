using Bunit;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;
using AddProjectPage = JidokaUi.Web.Components.Pages.AddProject;

namespace JidokaUi.Tests.Projects;

/// <summary>The add-project page as a browser draws it, over a registry that can be busy.</summary>
public sealed class AddProjectMarkupTests : BunitContext
{
    private readonly TempDirectory temp = new();

    [Fact]
    public void SaysTheRegistryIsBusyAndAddsNothingWhenTheAddFindsTheRegistryBusy()
    {
        var repository = temp.CreateSubdirectory("campfire");
        Directory.CreateDirectory(Path.Combine(repository, ".beads"));
        var store = new InMemoryProjectRegistryStore { Busy = true };
        Services.AddSingleton(new ProjectCatalog(store, new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System)));
        var page = Render<AddProjectPage>();
        page.Find("input[aria-label='Path']").Input(repository);
        page.FindAll("button").Single(button => button.TextContent == "Go").Click();

        page.FindAll("button").Single(button => button.TextContent == "Add this directory").Click();

        page.WaitForAssertion(() =>
            Assert.Equal("The registry is busy. Try again.", page.Find(".browser-refusal").TextContent));
        Assert.Empty(store.Load().Projects);
    }

    [Fact]
    public void ListsTheSubdirectoriesOfATypedPathAndMarksTheOneThatHoldsABeadsDirectory()
    {
        var repository = temp.CreateSubdirectory("campfire");
        Directory.CreateDirectory(Path.Combine(repository, ".beads"));
        temp.CreateSubdirectory("not-a-project");
        Services.AddSingleton(new ProjectCatalog(
            new InMemoryProjectRegistryStore(),
            new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System)));
        var page = Render<AddProjectPage>();

        page.Find("input[aria-label='Path']").Input(temp.Path);
        page.FindAll("button").Single(button => button.TextContent == "Go").Click();

        page.WaitForAssertion(() =>
        {
            var rows = page.FindAll(".browser-row");
            Assert.Equal(
                [".. (up one level)", "campfire", "not-a-project"],
                rows.Select(row => row.QuerySelector(".browser-name")?.TextContent));
            Assert.Equal(
                ["campfire"],
                rows.Where(row => row.QuerySelector(".badge")?.TextContent == "beads project")
                    .Select(row => row.QuerySelector(".browser-name")?.TextContent));
        });
    }

    protected override void Dispose(bool disposing)
    {
        temp.Dispose();
        base.Dispose(disposing);
    }
}
