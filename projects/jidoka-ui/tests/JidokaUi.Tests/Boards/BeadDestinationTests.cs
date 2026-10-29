using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;
using JidokaUi.Tests.Projects;

namespace JidokaUi.Tests.Boards;

public sealed class BeadDestinationTests
{
    private static readonly ProjectPath First = ProjectPath.From(Path.Combine(Path.GetTempPath(), "first"));
    private static readonly ProjectPath Second = ProjectPath.From(Path.Combine(Path.GetTempPath(), "second"));

    [Fact]
    public void LeadsToTheDetailPageOfTheBeadAndNamesTheProjectThatHoldsIt()
    {
        var destination = BeadDestination.Of(CatalogOver(AStoreHolding(First, Second)), new BeadAddress(Second, "b-7"));

        Assert.True(destination.Reaches);
        Assert.Equal($"bead/b-7?project={Uri.EscapeDataString(Second.Value)}", destination.Path);
    }

    [Fact]
    public void LeadsNowhereWhenTheRegistryLostTheProject()
    {
        var destination = BeadDestination.Of(CatalogOver(AStoreHolding(First)), new BeadAddress(Second, "b-7"));

        Assert.False(destination.Reaches);
        Assert.Contains("second", destination.Message);
    }

    private static InMemoryProjectRegistryStore AStoreHolding(params ProjectPath[] projects)
    {
        var store = new InMemoryProjectRegistryStore();
        store.Hold(ProjectRegistry.Empty with { Projects = [.. projects] });
        return store;
    }

    private static ProjectCatalog CatalogOver(IProjectRegistryStore store) =>
        new(store, new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());
}
