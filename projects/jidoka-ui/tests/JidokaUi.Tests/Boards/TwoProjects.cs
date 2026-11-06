using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Look;
using JidokaUi.Core.Projects;
using JidokaUi.Tests;
using JidokaUi.Tests.Beads;
using JidokaUi.Tests.Jidoka;
using JidokaUi.Tests.Projects;
using JidokaUi.Web.Components.Pages;

namespace JidokaUi.Tests.Boards;

/// <summary>
/// Two projects of a registry, the bd that answers in each of them, and the services that every
/// page of the app reads. The needs-you view and the detail page both open a bead of the second
/// project while another one is active, so both tests stand on the same ground. A test scripts the
/// commands that its own page runs.
/// </summary>
public sealed class TwoProjects : IDisposable
{
    private readonly TempDirectory directory = new();

    public TwoProjects()
    {
        First = ProjectPath.From(directory.CreateSubdirectory("first"));
        Second = ProjectPath.From(directory.CreateSubdirectory("second"));
        Store = new InMemoryProjectRegistryStore();
        Store.Hold(new ProjectRegistry([First, Second], []));
        Adapter = new BdAdapter(Bd, Clock);
        Backlogs = new BacklogCache(new BacklogReader(Adapter), Adapter);
        Watchers = new ProjectWatchers(Backlogs, WriteReports);
        JidokaHome = directory.CreateSubdirectory("jidoka-home");
        Catalog = new ProjectCatalog(Store, Adapter, new OnboardedProjectFiles(new JidokaHome(JidokaHome)));
        Selection = new ActiveProjectSelection(Catalog);
        AnInstallOfJidoka(JidokaHome);
        Pages = new JidokaPages(new JidokaHome(JidokaHome));
        JidokaAdapter = new JidokaAdapter(Jidoka, Adapter, new JidokaHome(JidokaHome), Clock);
    }

    /// <summary>The program that starts jidoka's scripts, which a test scripts by command line.</summary>
    public FakeJidoka Jidoka { get; } = new();

    /// <summary>The adapter over <see cref="Jidoka"/>, which finds the install under <see cref="JidokaHome"/>.</summary>
    public JidokaAdapter JidokaAdapter { get; }

    private static void AnInstallOfJidoka(string home)
    {
        File.WriteAllText(Path.Combine(home, "settings.json"), """{"python": "/opt/python3"}""");
        Directory.CreateDirectory(Path.Combine(home, "plugins", "0.1.2", "jidoka", "scripts"));
    }

    /// <summary>A repo with a beads directory that jidoka has onboarded, as its repo settings say.</summary>
    public ProjectPath Onboarded(string name)
    {
        var repository = directory.CreateSubdirectory(name);
        Directory.CreateDirectory(Path.Combine(repository, ".beads"));
        var settingsFolder = Path.Combine(JidokaHome, "repos");
        Directory.CreateDirectory(settingsFolder);
        File.WriteAllText(
            Path.Combine(settingsFolder, $"{name}-1a2b3c4d.json"),
            System.Text.Json.JsonSerializer.Serialize(new Dictionary<string, string> { ["main_worktree"] = repository }));
        return ProjectPath.From(repository);
    }

    public ProjectPath First { get; }

    public ProjectPath Second { get; }

    public InMemoryProjectRegistryStore Store { get; }

    public FakeBd Bd { get; } = new FakeBd().Prints("ready --json", "[]").Prints("blocked --json", "[]");

    public BdAdapter Adapter { get; }

    public BacklogCache Backlogs { get; }

    public FakeWriteReports WriteReports { get; } = new();

    public ProjectWatchers Watchers { get; }

    public ProjectCatalog Catalog { get; }

    public ActiveProjectSelection Selection { get; }

    /// <summary>The folder that stands for jidoka's home, which holds the pages a test writes.</summary>
    public string JidokaHome { get; }

    public JidokaPages Pages { get; }

    /// <summary>Writes the page of a kind beside a bead of the second project, as jidoka's script would.</summary>
    public void WritesAPage(JidokaPageKind kind, string id, string html)
    {
        var folder = Directory.CreateDirectory(Path.Combine(JidokaHome, "pages", Second.DirectoryName)).FullName;
        File.WriteAllText(Path.Combine(folder, $"{kind.Word()}-{id}.html"), html);
    }

    /// <summary>Writes the commit message saved beside the gate page of an epic of the second project, as the gate script would.</summary>
    public void SavesAGateMessage(string id, string message)
    {
        var folder = Directory.CreateDirectory(Path.Combine(JidokaHome, "pages", Second.DirectoryName)).FullName;
        File.WriteAllText(Path.Combine(folder, $"gate-{id}-message.txt"), message);
    }

    /// <summary>The clock that a working mark and a re-read mark read, which a test moves by hand.</summary>
    public FakeTimeProvider Clock { get; } = new(new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));

    /// <summary>Takes a project out of the registry, as another window of the app can.</summary>
    public void Forget(ProjectPath project) =>
        Store.Hold(new ProjectRegistry([.. Store.Load().Projects.Where(held => !held.Equals(project))], []));

    /// <summary>Gives a page the services that it reads whichever page it is.</summary>
    public void RegisterOn(IServiceCollection services)
    {
        services.AddSingleton(Adapter);
        services.AddSingleton(Backlogs);
        services.AddSingleton(Watchers);
        services.AddSingleton(Catalog);
        services.AddSingleton(Selection);
        services.AddSingleton(Pages);
        services.AddSingleton(JidokaAdapter);
        services.AddSingleton(new CopyFeedback());
        services.AddSingleton<TimeProvider>(Clock);
        services.AddScoped<BeadOpener>();
        services.AddScoped<SwitchAddress>();
    }

    public void Dispose()
    {
        Watchers.Dispose();
        directory.Dispose();
    }
}
