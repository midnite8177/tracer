using TracerUi.Core.Beads;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;

namespace TracerUi.Tests.Projects;

public class ProjectCatalogTests
{
    [Fact]
    public async Task AddsAValidatedProjectAndListsIt()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "tracer");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady()));

        var result = await catalog.AddAsync(repository);

        Assert.True(result.IsValid);
        Assert.Equal(["tracer"], catalog.Projects().Select(project => project.DirectoryName));
    }

    [Fact]
    public async Task RefusesAPathThatDoesNotValidateAndKeepsTheRegistryEmpty()
    {
        using var temp = new TempDirectory();
        var notARepository = temp.CreateSubdirectory("plain-directory");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady()));

        var result = await catalog.AddAsync(notARepository);

        Assert.False(result.IsValid);
        Assert.Contains(".beads", result.Message);
        Assert.Empty(catalog.Projects());
    }

    [Fact]
    public async Task RefusesAProjectThatTheRegistryHoldsAlready()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "tracer");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady()));
        await catalog.AddAsync(repository);

        var result = await catalog.AddAsync(repository + Path.DirectorySeparatorChar);

        Assert.False(result.IsValid);
        Assert.Contains("already", result.Message);
        Assert.Single(catalog.Projects());
    }

    [Fact]
    public async Task FindsAProjectWhateverFormOfThePathTheCallerGives()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "tracer");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady()));
        await catalog.AddAsync(repository);

        var found = catalog.Find(ProjectPath.From(repository + Path.DirectorySeparatorChar));

        Assert.NotNull(found);
    }

    private static string Repository(TempDirectory temp, string name)
    {
        var repository = temp.CreateSubdirectory(name);
        Directory.CreateDirectory(Path.Combine(repository, ".beads"));
        return repository;
    }

    [Fact]
    public async Task RefusesADirectoryWhereBdReadyDoesNotAnswer()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "tracer");
        var bd = new FakeBd().Fails("ready --json", "no beads database found in this directory");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(bd));

        var result = await catalog.AddAsync(repository);

        Assert.False(result.IsValid);
        Assert.Contains("no beads database found", result.Message);
        Assert.Empty(catalog.Projects());
    }

    [Fact]
    public async Task GivesOneEntryForEachProjectAndMarksNoNameThatOneProjectAloneCarries()
    {
        using var temp = new TempDirectory();
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady()));
        await catalog.AddAsync(Repository(temp, "tracer"));
        await catalog.AddAsync(Repository(temp, "widgets"));

        var entries = catalog.Entries();

        Assert.Equal(["tracer", "widgets"], entries.Select(entry => entry.DirectoryName));
        Assert.All(entries, entry => Assert.False(entry.SharesItsName));
    }

    [Fact]
    public async Task MarksBothEntriesWhenTwoProjectsCarryTheSameDirectoryName()
    {
        using var temp = new TempDirectory();
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady()));
        await catalog.AddAsync(Repository(temp, Path.Combine("one", "tracer")));
        await catalog.AddAsync(Repository(temp, Path.Combine("two", "tracer")));
        await catalog.AddAsync(Repository(temp, "widgets"));

        var entries = catalog.Entries();

        Assert.Equal([true, true, false], entries.Select(entry => entry.SharesItsName));
    }

    [Fact]
    public async Task ShowsTheWholePathOfAMarkedEntryAndTheDirectoryNameOfEveryOtherOne()
    {
        using var temp = new TempDirectory();
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady()));
        var shared = Repository(temp, Path.Combine("one", "tracer"));
        await catalog.AddAsync(shared);
        await catalog.AddAsync(Repository(temp, Path.Combine("two", "tracer")));
        await catalog.AddAsync(Repository(temp, "widgets"));

        var entries = catalog.Entries();

        Assert.Equal(shared, entries[0].Name);
        Assert.Equal("widgets", entries[2].Name);
    }

    [Fact]
    public async Task MarksTwoNamesThatDifferInTheirCaseAloneAsOneName()
    {
        using var temp = new TempDirectory();
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady()));
        await catalog.AddAsync(Repository(temp, Path.Combine("one", "Tracer")));
        await catalog.AddAsync(Repository(temp, Path.Combine("two", "tracer")));

        var entries = catalog.Entries();

        Assert.Equal([true, true], entries.Select(entry => entry.SharesItsName));
    }
}
