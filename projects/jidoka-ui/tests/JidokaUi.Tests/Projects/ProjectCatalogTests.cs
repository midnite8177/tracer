using JidokaUi.Core.Beads;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;

namespace JidokaUi.Tests.Projects;

public sealed class ProjectCatalogTests
{
    [Fact]
    public async Task AddsAValidatedProjectAndListsIt()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "campfire");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());

        var result = await catalog.AddAsync(repository);

        Assert.True(result.IsValid);
        Assert.Equal(["campfire"], catalog.Projects().Select(project => project.DirectoryName));
    }

    [Fact]
    public async Task RefusesAPathThatDoesNotValidateAndKeepsTheRegistryEmpty()
    {
        using var temp = new TempDirectory();
        var notARepository = temp.CreateSubdirectory("plain-directory");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());

        var result = await catalog.AddAsync(notARepository);

        Assert.False(result.IsValid);
        Assert.Contains(".beads", result.Message);
        Assert.Empty(catalog.Projects());
    }

    [Fact]
    public async Task RefusesAProjectThatTheRegistryHoldsAlready()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "campfire");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());
        await catalog.AddAsync(repository);

        var result = await catalog.AddAsync(repository + Path.DirectorySeparatorChar);

        Assert.False(result.IsValid);
        Assert.Contains("already", result.Message);
        Assert.Single(catalog.Projects());
    }

    [Fact]
    public async Task AddsAProjectOnceWhenTwoAddsOfItWaitOnBdAtTheSameTime()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "campfire");
        var bd = new FakeBd().Holds("ready --json");
        var store = new InMemoryProjectRegistryStore();
        var catalog = new ProjectCatalog(store, new BdAdapter(bd, TimeProvider.System), new NoOnboardedProjects());

        var firstAdd = catalog.AddAsync(repository);
        var secondAdd = catalog.AddAsync(repository);
        bd.Answers("ready --json", "[]");
        var results = await Task.WhenAll(firstAdd, secondAdd);

        Assert.Single(catalog.Projects());
        Assert.Equal(1, store.Saves);
        Assert.Single(results, result => result.IsValid);
        Assert.Single(results, result => result.Message == "This project is in the registry already.");
    }

    [Fact]
    public async Task SaysTheRegistryIsBusyAndAddsNothingWhenTheStoreIsBusy()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "campfire");
        var store = new InMemoryProjectRegistryStore { Busy = true };
        var catalog = new ProjectCatalog(store, new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());

        var result = await catalog.AddAsync(repository);

        Assert.False(result.IsValid);
        Assert.Equal("The registry is busy. Try again.", result.Message);
        Assert.Empty(catalog.Projects());
    }

    [Fact]
    public async Task FindsAProjectWhateverFormOfThePathTheCallerGives()
    {
        using var temp = new TempDirectory();
        var repository = Repository(temp, "campfire");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());
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
        var repository = Repository(temp, "campfire");
        var bd = new FakeBd().Fails("ready --json", "no beads database found in this directory");
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(bd, TimeProvider.System), new NoOnboardedProjects());

        var result = await catalog.AddAsync(repository);

        Assert.False(result.IsValid);
        Assert.Contains("no beads database found", result.Message);
        Assert.Empty(catalog.Projects());
    }

    [Fact]
    public async Task GivesOneEntryForEachProjectAndMarksNoNameThatOneProjectAloneCarries()
    {
        using var temp = new TempDirectory();
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());
        await catalog.AddAsync(Repository(temp, "campfire"));
        await catalog.AddAsync(Repository(temp, "widgets"));

        var entries = catalog.Entries();

        Assert.Equal(["campfire", "widgets"], entries.Select(entry => entry.DirectoryName));
        Assert.All(entries, entry => Assert.False(entry.SharesItsName));
    }

    [Fact]
    public async Task MarksBothEntriesWhenTwoProjectsCarryTheSameDirectoryName()
    {
        using var temp = new TempDirectory();
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());
        await catalog.AddAsync(Repository(temp, Path.Combine("one", "campfire")));
        await catalog.AddAsync(Repository(temp, Path.Combine("two", "campfire")));
        await catalog.AddAsync(Repository(temp, "widgets"));

        var entries = catalog.Entries();

        Assert.Equal([true, true, false], entries.Select(entry => entry.SharesItsName));
    }

    [Fact]
    public async Task ShowsTheWholePathOfAMarkedEntryAndTheDirectoryNameOfEveryOtherOne()
    {
        using var temp = new TempDirectory();
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());
        var shared = Repository(temp, Path.Combine("one", "campfire"));
        await catalog.AddAsync(shared);
        await catalog.AddAsync(Repository(temp, Path.Combine("two", "campfire")));
        await catalog.AddAsync(Repository(temp, "widgets"));

        var entries = catalog.Entries();

        Assert.Equal(shared, entries[0].Name);
        Assert.Equal("widgets", entries[2].Name);
    }

    [Fact]
    public async Task MarksTwoNamesThatDifferInTheirCaseAloneAsOneName()
    {
        using var temp = new TempDirectory();
        var catalog = new ProjectCatalog(new InMemoryProjectRegistryStore(), new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System), new NoOnboardedProjects());
        await catalog.AddAsync(Repository(temp, Path.Combine("one", "Campfire")));
        await catalog.AddAsync(Repository(temp, Path.Combine("two", "campfire")));

        var entries = catalog.Entries();

        Assert.Equal([true, true], entries.Select(entry => entry.SharesItsName));
    }
}
