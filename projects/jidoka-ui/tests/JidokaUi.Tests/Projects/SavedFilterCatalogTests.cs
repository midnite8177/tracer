using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Projects;

public sealed class SavedFilterCatalogTests
{
    private static readonly ProjectPath Campfire = ProjectPath.From("/Users/someone/Projects/campfire");
    private static readonly ProjectPath Widgets = ProjectPath.From("/Users/someone/Projects/widgets");

    private static SavedFilterCatalog Over(IProjectRegistryStore store) => new(store);

    [Fact]
    public void ReadsBackAFilterThatItSavedUnderAName()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());

        catalog.Save(Campfire, "The bugs", BoardFilter.Everything with { Type = "bug" });

        var saved = Assert.Single(catalog.Filters(Campfire));
        Assert.Equal("The bugs", saved.Name);
        Assert.Equal("bug", saved.Filter.Type);
    }

    [Fact]
    public void ReplacesTheFilterThatANameAlreadyHeldInTheSameProject()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());

        catalog.Save(Campfire, "Triage", BoardFilter.Everything with { Type = "bug" });
        catalog.Save(Campfire, "Triage", BoardFilter.Everything with { Type = "task" });

        var saved = Assert.Single(catalog.Filters(Campfire));
        Assert.Equal("task", saved.Filter.Type);
    }

    [Fact]
    public void KeepsTheFiltersOfOneProjectOutOfAnother()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());

        catalog.Save(Campfire, "Triage", BoardFilter.Everything with { Epic = "Milestone one" });
        catalog.Save(Widgets, "Triage", BoardFilter.NeedsYou);

        Assert.Equal("Milestone one", Assert.Single(catalog.Filters(Campfire)).Filter.Epic);
        Assert.True(Assert.Single(catalog.Filters(Widgets)).Filter.RequiresHumanLabel);
    }

    [Fact]
    public void ForgetsAFilterThatItRemoves()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());
        catalog.Save(Campfire, "Triage", BoardFilter.NeedsYou);
        catalog.Save(Campfire, "Inventory", BoardFilter.NoDemoLine);

        catalog.Remove(Campfire, "Triage");

        Assert.Equal("Inventory", Assert.Single(catalog.Filters(Campfire)).Name);
    }

    [Fact]
    public void LeavesTheFilterOfAnotherProjectAloneWhenItRemovesOne()
    {
        var catalog = Over(new InMemoryProjectRegistryStore());
        catalog.Save(Campfire, "Triage", BoardFilter.NeedsYou);
        catalog.Save(Widgets, "Triage", BoardFilter.NoDemoLine);

        catalog.Remove(Campfire, "Triage");

        Assert.Single(catalog.Filters(Widgets));
    }

    [Fact]
    public void LeavesTheProjectsAloneWhenItSavesAFilter()
    {
        var store = new InMemoryProjectRegistryStore();
        store.Hold(new ProjectRegistry([Campfire], []));

        Over(store).Save(Campfire, "Triage", BoardFilter.NeedsYou);

        Assert.Single(store.Load().Projects);
    }

    [Fact]
    public void WritesNothingWhenItRemovesANameThatNoFilterHolds()
    {
        var store = new InMemoryProjectRegistryStore();
        Over(store).Save(Campfire, "Triage", BoardFilter.NeedsYou);
        var savesAfterTheFilter = store.Saves;

        Over(store).Remove(Campfire, "Inventory");

        Assert.Equal(savesAfterTheFilter, store.Saves);
    }

    [Fact]
    public void AnswersBusyAndKeepsNoFilterWhenTheStoreIsBusy()
    {
        var store = new InMemoryProjectRegistryStore { Busy = true };

        var outcome = Over(store).Save(Campfire, "Triage", BoardFilter.NeedsYou);

        Assert.Equal(RegistryUpdate.Busy, outcome);
        Assert.Empty(Over(store).Filters(Campfire));
    }

    [Fact]
    public void AnswersBusyAndKeepsTheFilterWhenTheStoreIsBusyAtARemove()
    {
        var store = new InMemoryProjectRegistryStore();
        Over(store).Save(Campfire, "Triage", BoardFilter.NeedsYou);
        store.Busy = true;

        var outcome = Over(store).Remove(Campfire, "Triage");

        Assert.Equal(RegistryUpdate.Busy, outcome);
        Assert.Single(Over(store).Filters(Campfire));
    }
}
