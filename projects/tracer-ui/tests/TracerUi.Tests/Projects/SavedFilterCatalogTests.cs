using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Projects;

public sealed class SavedFilterCatalogTests
{
    private static readonly ProjectPath Tracer = ProjectPath.From("/Users/someone/Projects/tracer");
    private static readonly ProjectPath Widgets = ProjectPath.From("/Users/someone/Projects/widgets");

    private static SavedFilterCatalog Over(IProjectRegistryStore store) => new(store);

    [Fact]
    public void ReadsBackAFilterThatItSavedUnderAName()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());

        catalog.Save(Tracer, "The bugs", BoardFilter.Everything with { Type = "bug" });

        var saved = Assert.Single(catalog.Filters(Tracer));
        Assert.Equal("The bugs", saved.Name);
        Assert.Equal("bug", saved.Filter.Type);
    }

    [Fact]
    public void ReplacesTheFilterThatANameAlreadyHeldInTheSameProject()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());

        catalog.Save(Tracer, "Triage", BoardFilter.Everything with { Type = "bug" });
        catalog.Save(Tracer, "Triage", BoardFilter.Everything with { Type = "task" });

        var saved = Assert.Single(catalog.Filters(Tracer));
        Assert.Equal("task", saved.Filter.Type);
    }

    [Fact]
    public void KeepsTheFiltersOfOneProjectOutOfAnother()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());

        catalog.Save(Tracer, "Triage", BoardFilter.Everything with { Epic = "Milestone one" });
        catalog.Save(Widgets, "Triage", BoardFilter.NeedsYou);

        Assert.Equal("Milestone one", Assert.Single(catalog.Filters(Tracer)).Filter.Epic);
        Assert.True(Assert.Single(catalog.Filters(Widgets)).Filter.RequiresHumanLabel);
    }

    [Fact]
    public void ForgetsAFilterThatItRemoves()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());
        catalog.Save(Tracer, "Triage", BoardFilter.NeedsYou);
        catalog.Save(Tracer, "Inventory", BoardFilter.NoDemoLine);

        catalog.Remove(Tracer, "Triage");

        Assert.Equal("Inventory", Assert.Single(catalog.Filters(Tracer)).Name);
    }

    [Fact]
    public void LeavesTheFilterOfAnotherProjectAloneWhenItRemovesOne()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());
        catalog.Save(Tracer, "Triage", BoardFilter.NeedsYou);
        catalog.Save(Widgets, "Triage", BoardFilter.NoDemoLine);

        catalog.Remove(Tracer, "Triage");

        Assert.Single(catalog.Filters(Widgets));
    }

    [Fact]
    public void LeavesTheProjectsAloneWhenItSavesAFilter()
    {
        var store = new InMemoryProjectRegistryStore();
        store.Save(new ProjectRegistry([Tracer], []));

        Over(store).Save(Tracer, "Triage", BoardFilter.NeedsYou);

        Assert.Single(store.Load().Projects);
    }

    [Fact]
    public void WritesNothingWhenItRemovesANameThatNoFilterHolds()
    {
        var store = new InMemoryProjectRegistryStore();
        Over(store).Save(Tracer, "Triage", BoardFilter.NeedsYou);
        var savesAfterTheFilter = store.Saves;

        Over(store).Remove(Tracer, "Inventory");

        Assert.Equal(savesAfterTheFilter, store.Saves);
    }
}
