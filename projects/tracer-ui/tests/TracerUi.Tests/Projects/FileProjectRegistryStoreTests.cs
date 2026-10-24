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
        var store = new FileProjectRegistryStore(Path.Combine(temp.Path, "registry.json"), Signals.LongEnough);
        var saved = new ProjectRegistry(
            [
                ProjectPath.From("/Users/someone/Projects/tracer"),
                ProjectPath.From("/Users/someone/Projects/widgets"),
            ],
            []);

        store.Update(registry => saved);
        var loaded = store.Load();

        Assert.Equal(saved.Projects, loaded.Projects);
    }

    [Fact]
    public void LoadsAnEmptyRegistryWhenTheFileDoesNotExist()
    {
        using var temp = new TempDirectory();
        var store = new FileProjectRegistryStore(Path.Combine(temp.Path, "registry.json"), Signals.LongEnough);

        var loaded = store.Load();

        Assert.Empty(loaded.Projects);
    }

    [Fact]
    public void CreatesTheDirectoryOfTheRegistryFileOnTheFirstUpdate()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "config", "tracer-ui", "registry.json");
        var store = new FileProjectRegistryStore(filePath, Signals.LongEnough);

        store.Update(registry => new ProjectRegistry([ProjectPath.From("/Users/someone/Projects/tracer")], []));

        Assert.True(File.Exists(filePath));
    }

    [Fact]
    public void LoadsBackTheSavedFiltersThroughANewStoreOverTheSameFile()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "registry.json");
        new FileProjectRegistryStore(filePath, Signals.LongEnough).Update(registry => new ProjectRegistry(
            [],
            [
                new SavedFilter(
                    ProjectPath.From("/Users/someone/Projects/tracer"),
                    "Triage",
                    BoardFilter.Everything with { Type = "bug", Text = "watcher" }),
            ]));

        var loaded = new FileProjectRegistryStore(filePath, Signals.LongEnough).Load();

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

    [Fact]
    public async Task KeepsTheProjectOfAnUpdateThatAnotherStoreOverTheSameFileMadeWhileThisOneWaited()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "projects.json");
        var first = new FileProjectRegistryStore(filePath, Signals.LongEnough);
        var second = new FileProjectRegistryStore(filePath, Signals.LongEnough);
        using var firstHasRead = new ManualResetEventSlim();
        using var firstMayWrite = new ManualResetEventSlim();

        var firstUpdate = Task.Run(() => first.Update(registry =>
        {
            firstHasRead.Set();
            firstMayWrite.Wait(Signals.LongEnough);
            return registry with { Projects = [.. registry.Projects, Tracer] };
        }));
        Assert.True(firstHasRead.Wait(Signals.LongEnough));
        var secondUpdate = Task.Run(() => second.Update(registry => registry with { Projects = [.. registry.Projects, Widgets] }));

        var firstToFinish = await Task.WhenAny(secondUpdate, Task.Delay(TimeSpan.FromMilliseconds(300)));
        Assert.NotSame(secondUpdate, firstToFinish);
        firstMayWrite.Set();

        Assert.Equal(RegistryUpdate.Written, await firstUpdate.WaitAsync(Signals.LongEnough));
        Assert.Equal(RegistryUpdate.Written, await secondUpdate.WaitAsync(Signals.LongEnough));
        Assert.Equal([Tracer, Widgets], new FileProjectRegistryStore(filePath, Signals.LongEnough).Load().Projects);
    }

    [Fact]
    public async Task AnswersBusyAndWritesNothingWhenAnotherStoreHoldsTheRegistryForTheWholeTimeout()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "projects.json");
        var holder = new FileProjectRegistryStore(filePath, Signals.LongEnough);
        var waiter = new FileProjectRegistryStore(filePath, TimeSpan.FromMilliseconds(100));
        using var holderHasRead = new ManualResetEventSlim();
        using var holderMayWrite = new ManualResetEventSlim();
        var holderUpdate = Task.Run(() => holder.Update(registry =>
        {
            holderHasRead.Set();
            holderMayWrite.Wait(Signals.LongEnough);
            return registry with { Projects = [.. registry.Projects, Tracer] };
        }));
        Assert.True(holderHasRead.Wait(Signals.LongEnough));
        var changeRan = false;

        var outcome = waiter.Update(registry =>
        {
            changeRan = true;
            return registry with { Projects = [.. registry.Projects, Widgets] };
        });
        holderMayWrite.Set();
        await holderUpdate.WaitAsync(Signals.LongEnough);

        Assert.Equal(RegistryUpdate.Busy, outcome);
        Assert.False(changeRan);
        Assert.Equal([Tracer], holder.Load().Projects);
    }

    [Fact]
    public void LeavesTheRegistryFileAsItWasWhenTheChangeThrows()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "projects.json");
        var store = new FileProjectRegistryStore(filePath, Signals.LongEnough);
        store.Update(registry => registry with { Projects = [Tracer] });
        var before = File.ReadAllText(filePath);

        Assert.Throws<InvalidOperationException>(() =>
            store.Update(registry => throw new InvalidOperationException("The change gave up.")));

        Assert.Equal(before, File.ReadAllText(filePath));
    }

    [Fact]
    public void LetsAnotherStoreUpdateTheRegistryAfterAChangeThrew()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "projects.json");
        var store = new FileProjectRegistryStore(filePath, Signals.LongEnough);
        Assert.Throws<InvalidOperationException>(() =>
            store.Update(registry => throw new InvalidOperationException("The change gave up.")));

        var outcome = new FileProjectRegistryStore(filePath, TimeSpan.FromMilliseconds(100))
            .Update(registry => registry with { Projects = [Widgets] });

        Assert.Equal(RegistryUpdate.Written, outcome);
        Assert.Equal([Widgets], store.Load().Projects);
    }

    [Fact]
    public void WritesNoRegistryFileWhenTheChangeGivesNoRegistry()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "projects.json");

        var outcome = new FileProjectRegistryStore(filePath, Signals.LongEnough).Update(registry => null);

        Assert.Equal(RegistryUpdate.Unchanged, outcome);
        Assert.False(File.Exists(filePath));
    }

    [Fact]
    public async Task KeepsEveryProjectThatTwoStoresOverTheSameFileAddAtOnce()
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "projects.json");
        var first = new FileProjectRegistryStore(filePath, Signals.LongEnough);
        var second = new FileProjectRegistryStore(filePath, Signals.LongEnough);
        var firstProjects = Enumerable.Range(0, 25).Select(n => ProjectPath.From($"/Users/someone/first/{n}")).ToArray();
        var secondProjects = Enumerable.Range(0, 25).Select(n => ProjectPath.From($"/Users/someone/second/{n}")).ToArray();

        await Task.WhenAll(
            Task.Run(() => AddEach(first, firstProjects)),
            Task.Run(() => AddEach(second, secondProjects))).WaitAsync(Signals.LongEnough);

        Assert.Equal(
            firstProjects.Concat(secondProjects).Select(project => project.Value).Order(StringComparer.Ordinal),
            first.Load().Projects.Select(project => project.Value).Order(StringComparer.Ordinal));
    }

    private static void AddEach(FileProjectRegistryStore store, IEnumerable<ProjectPath> projects)
    {
        foreach (var project in projects)
        {
            store.Update(registry => registry with { Projects = [.. registry.Projects, project] });
        }
    }

    private static readonly ProjectPath Tracer = ProjectPath.From("/Users/someone/Projects/tracer");

    private static readonly ProjectPath Widgets = ProjectPath.From("/Users/someone/Projects/widgets");

    private static ProjectRegistry LoadFrom(string registryFile)
    {
        using var temp = new TempDirectory();
        var filePath = Path.Combine(temp.Path, "registry.json");
        File.WriteAllText(filePath, registryFile);

        return new FileProjectRegistryStore(filePath, Signals.LongEnough).Load();
    }
}
