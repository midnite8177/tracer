using Bunit;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Beads;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;
using AddProjectPage = TracerUi.Web.Components.Pages.AddProject;

namespace TracerUi.Tests.Projects;

/// <summary>The add-project page as a browser draws it, over a registry that can be busy.</summary>
public sealed class AddProjectMarkupTests : BunitContext
{
    private readonly TempDirectory temp = new();

    [Fact]
    public void SaysTheRegistryIsBusyAndAddsNothingWhenTheAddFindsTheRegistryBusy()
    {
        var repository = temp.CreateSubdirectory("tracer");
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

    protected override void Dispose(bool disposing)
    {
        temp.Dispose();
        base.Dispose(disposing);
    }
}
