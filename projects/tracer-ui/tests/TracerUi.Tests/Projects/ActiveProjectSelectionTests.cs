using TracerUi.Core.Beads;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;

namespace TracerUi.Tests.Projects;

public class ActiveProjectSelectionTests
{
    [Fact]
    public void HasNoActiveProjectBeforeAChoice()
    {
        var selection = new ActiveProjectSelection(new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System)));

        Assert.Null(selection.Current);
    }

    [Fact]
    public async Task MakesARegisteredProjectTheActiveOne()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer", "widgets");
        var selection = new ActiveProjectSelection(catalog);

        var chosen = selection.Select(ProjectPath.From(Path.Combine(temp.Path, "widgets")));

        Assert.True(chosen);
        Assert.Equal("widgets", selection.Current?.DirectoryName);
    }

    [Fact]
    public async Task KeepsTheActiveProjectWhenThePathIsNotInTheRegistry()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer");
        var selection = new ActiveProjectSelection(catalog);
        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "tracer")));

        var chosen = selection.Select(ProjectPath.From(Path.Combine(temp.Path, "unknown")));

        Assert.False(chosen);
        Assert.Equal("tracer", selection.Current?.DirectoryName);
    }

    [Fact]
    public async Task TellsTheChromeAndThePagesWhenTheActiveProjectBecomesAnotherOne()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer", "widgets");
        var selection = new ActiveProjectSelection(catalog);
        var announced = new List<string>();
        selection.Changed += change => announced.Add(change.Project.DirectoryName);

        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "widgets")));

        Assert.Equal(["widgets"], announced);
    }

    [Fact]
    public async Task CallsAPickInTheTopBarASwitchThatAPersonMade()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer", "widgets");
        var selection = new ActiveProjectSelection(catalog);
        var announced = new List<ActiveProjectChange>();
        selection.Changed += announced.Add;

        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "widgets")));

        Assert.Equal(ActiveProjectChangeKind.Switch, Assert.Single(announced).Kind);
    }

    [Fact]
    public async Task CallsThePathThatTheBrowserHeldARestoreAndNoSwitch()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer", "widgets");
        var selection = new ActiveProjectSelection(catalog);
        var announced = new List<ActiveProjectChange>();
        selection.Changed += announced.Add;

        selection.Restore(Path.Combine(temp.Path, "widgets"));

        Assert.Equal(ActiveProjectChangeKind.Restore, Assert.Single(announced).Kind);
    }

    [Fact]
    public async Task SaysNothingWhenThePickIsTheProjectThatIsActiveAlready()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer");
        var selection = new ActiveProjectSelection(catalog);
        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "tracer")));
        var announced = new List<string>();
        selection.Changed += change => announced.Add(change.Project.DirectoryName);

        selection.Select(ProjectPath.From(Path.Combine(temp.Path, "tracer")));

        Assert.Empty(announced);
    }

    [Fact]
    public async Task RestoresTheProjectThatTheBrowserStored()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer", "widgets");
        var selection = new ActiveProjectSelection(catalog);

        var restored = selection.Restore(Path.Combine(temp.Path, "widgets"));

        Assert.True(restored);
        Assert.Equal("widgets", selection.Current?.DirectoryName);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("   ")]
    public async Task TakesNoProjectWhenTheBrowserStoredNoPath(string? stored)
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer");
        var selection = new ActiveProjectSelection(catalog);

        var restored = selection.Restore(stored);

        Assert.False(restored);
        Assert.Null(selection.Current);
    }

    [Fact]
    public async Task TakesNoProjectWhenTheStoredPathLeftTheRegistry()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer");
        var selection = new ActiveProjectSelection(catalog);

        var restored = selection.Restore(Path.Combine(temp.Path, "widgets"));

        Assert.False(restored);
        Assert.Null(selection.Current);
    }

    [Fact]
    public async Task TakesNoProjectWhenTheStoredPathIsNoPathAtAll()
    {
        using var temp = new TempDirectory();
        var catalog = await CatalogWithProjects(temp, "tracer");
        var selection = new ActiveProjectSelection(catalog);

        var restored = selection.Restore("a path with \0 in it");

        Assert.False(restored);
        Assert.Null(selection.Current);
    }

    private static async Task<ProjectCatalog> CatalogWithProjects(TempDirectory temp, params string[] names)
    {
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System));
        foreach (var name in names)
        {
            var repository = temp.CreateSubdirectory(name);
            Directory.CreateDirectory(Path.Combine(repository, ".beads"));
            await catalog.AddAsync(repository);
        }

        return catalog;
    }
}
