using JidokaUi.Core.Beads;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Projects;
using JidokaUi.Tests.Beads;

namespace JidokaUi.Tests.Projects;

public sealed class OnboardedProjectsTests : IDisposable
{
    private readonly TempDirectory temp = new();
    private readonly string jidokaHome;
    private readonly InMemoryProjectRegistryStore store = new();

    public OnboardedProjectsTests()
    {
        jidokaHome = temp.CreateSubdirectory("jidoka-home");
    }

    public void Dispose() => temp.Dispose();

    [Fact]
    public void ListsEveryRepoThatJidokaOnboardedWithNoSecondStep()
    {
        var campfire = Repository("campfire");
        var widgets = Repository("widgets");
        Onboard("campfire-1a2b3c4d", campfire);
        Onboard("widgets-5e6f7a8b", widgets);

        var projects = Catalog().Projects();

        Assert.Equal([ProjectPath.From(campfire), ProjectPath.From(widgets)], projects);
    }

    [Fact]
    public void ListsARepoOnceWhenThePersonAddedItAndJidokaOnboardedItToo()
    {
        var repository = Repository("campfire");
        Onboard("campfire-1a2b3c4d", repository);
        var catalog = Catalog();
        store.Hold(new ProjectRegistry([ProjectPath.From(repository)], []));

        Assert.Single(catalog.Projects());
        Assert.Single(catalog.Entries());
    }

    [Fact]
    public void FindsAnOnboardedRepoByItsPath()
    {
        var repository = Repository("campfire");
        Onboard("campfire-1a2b3c4d", repository);

        var found = Catalog().Find(ProjectPath.From(repository + Path.DirectorySeparatorChar));

        Assert.NotNull(found);
    }

    [Fact]
    public void ListsNothingWhenJidokaHasOnboardedNoRepo()
    {
        Assert.Empty(Catalog().Projects());
    }

    [Fact]
    public void SkipsASettingsFileThatIsNotJsonAndKeepsTheOtherRepos()
    {
        var repository = Repository("campfire");
        Directory.CreateDirectory(Path.Combine(jidokaHome, "repos"));
        File.WriteAllText(Path.Combine(jidokaHome, "repos", "a-broken-00000000.json"), "{ not json");
        File.WriteAllText(Path.Combine(jidokaHome, "repos", "no-key-11111111.json"), """{"lap_limit": 2}""");
        File.WriteAllText(Path.Combine(jidokaHome, "repos", "relative-22222222.json"), """{"main_worktree": "campfire"}""");
        Onboard("campfire-1a2b3c4d", repository);

        Assert.Equal([ProjectPath.From(repository)], Catalog().Projects());
    }

    [Fact]
    public void SkipsAnOnboardedRepoWhoseFolderHoldsNoBeadsDirectory()
    {
        Onboard("gone-1a2b3c4d", Path.Combine(temp.Path, "moved-away"));
        var plain = temp.CreateSubdirectory("plain");
        Onboard("plain-5e6f7a8b", plain);

        Assert.Empty(Catalog().Projects());
    }

    [Fact]
    public async Task RefusesToAddARepoThatJidokaOnboardedAndWritesNoRegistry()
    {
        var repository = Repository("campfire");
        Onboard("campfire-1a2b3c4d", repository);

        var result = await Catalog().AddAsync(repository);

        Assert.False(result.IsValid);
        Assert.Contains("onboarded", result.Message);
        Assert.Equal(0, store.Saves);
    }

    [Fact]
    public async Task WritesNothingUnderJidokasHomeWhenItListsFindsAndRefusesAnOnboardedRepo()
    {
        var repository = Repository("campfire");
        Onboard("campfire-1a2b3c4d", repository);
        var before = Snapshot();
        var catalog = Catalog();

        _ = catalog.Projects();
        _ = catalog.Entries();
        _ = catalog.Find(ProjectPath.From(repository));
        await catalog.AddAsync(repository);

        Assert.Equal(before, Snapshot());
    }

    private ProjectCatalog Catalog() => new(
        store,
        new BdAdapter(FakeBd.ThatAnswersReady(), TimeProvider.System),
        new OnboardedProjectFiles(new JidokaHome(jidokaHome)));

    private string Repository(string name)
    {
        var repository = temp.CreateSubdirectory(name);
        Directory.CreateDirectory(Path.Combine(repository, ".beads"));
        return repository;
    }

    private void Onboard(string fileStem, string mainWorktree)
    {
        var folder = Path.Combine(jidokaHome, "repos");
        Directory.CreateDirectory(folder);
        var settings = new Dictionary<string, object>
        {
            ["main_worktree"] = mainWorktree,
            ["lap_limit"] = 2,
        };
        File.WriteAllText(Path.Combine(folder, fileStem + ".json"), System.Text.Json.JsonSerializer.Serialize(settings));
    }

    private Dictionary<string, string> Snapshot() =>
        Directory.EnumerateFiles(jidokaHome, "*", SearchOption.AllDirectories)
            .ToDictionary(file => file, File.ReadAllText);
}
