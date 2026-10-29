using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;

namespace JidokaUi.Tests.Projects;

public class ActiveProjectSelectionTests
{
    [Fact]
    public void HasNoActiveProjectBeforeAChoice()
    {
        var selection = new ActiveProjectSelection(new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects()));

        Assert.Null(selection.Current);
    }

    [Fact]
    public async Task MakesARegisteredProjectTheActiveOne()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "campfire", "widgets");
        var selection = new ActiveProjectSelection(catalog);

        var chosen = selection.Select(ProjectPath.From(Path.Combine(temp.Path, "widgets")));

        Assert.True(chosen);
        Assert.Equal("widgets", selection.Current?.DirectoryName);
    }

    [Fact]
    public async Task KeepsTheActiveProjectWhenThePathIsNotInTheRegistry()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "campfire");
        var selection = new ActiveProjectSelection(catalog);
        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "campfire")));

        var chosen = selection.Select(ProjectPath.From(Path.Combine(temp.Path, "unknown")));

        Assert.False(chosen);
        Assert.Equal("campfire", selection.Current?.DirectoryName);
    }

    [Fact]
    public async Task TellsTheChromeAndThePagesWhenTheActiveProjectBecomesAnotherOne()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "campfire", "widgets");
        var selection = new ActiveProjectSelection(catalog);
        var announced = new List<string>();
        selection.Changed += project => announced.Add(project.DirectoryName);

        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "widgets")));

        Assert.Equal(["widgets"], announced);
    }

    [Fact]
    public async Task MakesAnotherRegisteredProjectActiveOverTheOneThatTheTabRemembers()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "campfire", "widgets");
        var selection = new ActiveProjectSelection(catalog);
        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "campfire")));
        var announced = new List<string>();
        selection.Changed += project => announced.Add(project.DirectoryName);

        var chosen = selection.Select(ProjectPath.From(Path.Combine(temp.Path, "widgets")));

        Assert.True(chosen);
        Assert.Equal("widgets", selection.Current?.DirectoryName);
        Assert.Equal(["widgets"], announced);
    }

    [Fact]
    public async Task SaysNothingWhenThePickIsTheProjectThatIsActiveAlready()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "campfire");
        var selection = new ActiveProjectSelection(catalog);
        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "campfire")));
        var announced = new List<string>();
        selection.Changed += project => announced.Add(project.DirectoryName);

        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "campfire")));

        Assert.Empty(announced);
    }

    private static async Task<ProjectCatalog> CatalogWithProjects(TempDirectory temp, params string[] names)
    {
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());
        foreach (var name in names)
        {
            var repository = temp.CreateSubdirectory(name);
            Directory.CreateDirectory(Path.Combine(repository, ".beads"));
            await catalog.AddAsync(repository);
        }

        return catalog;
    }
}
