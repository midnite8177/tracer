using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using TracerUi.Tests.Boards;

namespace TracerUi.Tests.Projects;

public class FileProjectRegistryStoreTests
{
    [Fact]
    public void LoadsBackTheProjectsThatItSaved()
    {
        using var temp = new TempDirectory();
        var store = new FileProjectRegistryStore(Path.Combine(temp.Path, "registry.json"));
        var saved = new ProjectRegistry(
            [
                ProjectPath.From("/Users/someone/Projects/tracer"),
                ProjectPath.From("/Users/someone/Projects/widgets"),
            ],
            []);

        store.Save(saved);
        var loaded = store.Load();

        Assert.Equal(saved.Projects, loaded.Projects);
    }

    [Fact]
    public void LoadsAnEmptyRegistryWhenTheFileDoesNotExist()
    {
        using var temp = new TempDirectory();
        var store = new FileProjectRegistryStore(Path.Combine(temp.Path, "registry.json"));

        var loaded = store.Load();

        Assert.Empty(loaded.Projects);
    }

    [Fact]
    public void CreatesTheDirectoryOfTheRegistryFileOnTheFirstSave()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "config", "tracer-ui", "registry.json");
        var store = new FileProjectRegistryStore(filePath);

        store.Save(new ProjectRegistry([ProjectPath.From("/Users/someone/Projects/tracer")], []));

        Assert.True(File.Exists(filePath));
    }

    [Fact]
    public void LoadsBackTheSavedFiltersThroughANewStoreOverTheSameFile()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "registry.json");
        new FileProjectRegistryStore(filePath).Save(new ProjectRegistry(
            [],
            [
                new SavedFilter(
                    ProjectPath.From("/Users/someone/Projects/tracer"),
                    "Triage",
                    BoardFilter.Everything with { Type = "bug", Text = "watcher" }),
            ]));

        var loaded = new FileProjectRegistryStore(filePath).Load();

        var saved = Assert.Single(loaded.SavedFilters);
        Assert.Equal(ProjectPath.From("/Users/someone/Projects/tracer"), saved.Project);
        Assert.Equal("Triage", saved.Name);
        Assert.Equal("bug", saved.Filter.Type);
        Assert.Equal("watcher", saved.Filter.Text);
    }

    [Fact]
    public void KeepsEveryBeadForAPartThatTheRegistryFileOfASavedFilterDoesNotName()
    {
        var saved = Assert.Single(LoadFrom("""
            {"projects": ["/Users/someone/Projects/tracer"],
             "savedFilters": [{"project": "/Users/someone/Projects/tracer",
                               "name": "Triage",
                               "filter": {"type": "bug"}}]}
            """).SavedFilters);

        Assert.True(saved.Filter.Matches(ABead.Called("x-1", "A bug") with { Type = "bug" }, []));
    }

    [Fact]
    public void LoadsNoSavedFilterFromARegistryFileThatNamesOnlyProjects()
    {
        var loaded = LoadFrom("""{"projects": ["/Users/someone/Projects/tracer"]}""");

        Assert.Single(loaded.Projects);
        Assert.Empty(loaded.SavedFilters);
    }

    [Fact]
    public void KeepsEveryBeadForASavedFilterThatTheRegistryFileNamesWithNoFilter()
    {
        var saved = Assert.Single(LoadFrom("""
            {"savedFilters": [{"project": "/Users/someone/Projects/tracer",
                               "name": "Triage"}]}
            """).SavedFilters);

        Assert.True(saved.Filter.Matches(ABead.Called("x-1", "Anything"), []));
    }

    [Fact]
    public void LoadsNoSavedFilterFromARegistryEntryThatNamesNoProject()
    {
        var loaded = LoadFrom("""{"savedFilters": [{"name": "Triage", "filter": {"type": "bug"}}]}""");

        Assert.Empty(loaded.SavedFilters);
    }

    [Fact]
    public void LoadsNoSavedFilterFromARegistryEntryThatNamesNoName()
    {
        var loaded = LoadFrom("""
            {"savedFilters": [{"project": "/Users/someone/Projects/tracer", "filter": {"type": "bug"}}]}
            """);

        Assert.Empty(loaded.SavedFilters);
    }

    [Fact]
    public void LoadsNoProjectFromARegistryFileThatNamesOneAsNothing()
    {
        var loaded = LoadFrom("""{"projects": [null, "/Users/someone/Projects/tracer"]}""");

        Assert.Equal([ProjectPath.From("/Users/someone/Projects/tracer")], loaded.Projects);
    }

    private static ProjectRegistry LoadFrom(string registryFile)
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "registry.json");
        File.WriteAllText(filePath, registryFile);

        return new FileProjectRegistryStore(filePath).Load();
    }
}
