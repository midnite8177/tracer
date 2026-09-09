using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Look;
using TracerUi.Core.Projects;
using TracerUi.Tests;
using TracerUi.Tests.Beads;
using TracerUi.Tests.Projects;
using TracerUi.Web.Components.Pages;

namespace TracerUi.Tests.Boards;

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
        Store.Save(new ProjectRegistry([First, Second], []));
        Adapter = new BdAdapter(Bd, Clock);
        Backlogs = new BacklogCache(new BacklogReader(Adapter), Adapter);
        Catalog = new ProjectCatalog(Store, Adapter);
        Selection = new ActiveProjectSelection(Catalog);
    }

    public ProjectPath First { get; }

    public ProjectPath Second { get; }

    public InMemoryProjectRegistryStore Store { get; }

    public FakeBd Bd { get; } = new FakeBd().Prints("ready --json", "[]").Prints("blocked --json", "[]");

    public BdAdapter Adapter { get; }

    public BacklogCache Backlogs { get; }

    public ProjectCatalog Catalog { get; }

    public ActiveProjectSelection Selection { get; }

    /// <summary>The clock that a working mark and a re-read mark read, which a test moves by hand.</summary>
    public FakeTimeProvider Clock { get; } = new(new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));

    /// <summary>Takes a project out of the registry, as another window of the app can.</summary>
    public void Forget(ProjectPath project) =>
        Store.Save(new ProjectRegistry([.. Store.Load().Projects.Where(held => !held.Equals(project))], []));

    /// <summary>Gives a page the services that it reads whichever page it is.</summary>
    public void RegisterOn(IServiceCollection services)
    {
        services.AddSingleton(Adapter);
        services.AddSingleton(Backlogs);
        services.AddSingleton(Catalog);
        services.AddSingleton(Selection);
        services.AddSingleton(new CopyFeedback());
        services.AddSingleton<TimeProvider>(Clock);
        services.AddScoped<BeadOpener>();
    }

    public void Dispose() => directory.Dispose();
}
