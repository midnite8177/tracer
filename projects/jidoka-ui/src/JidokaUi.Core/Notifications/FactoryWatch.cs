using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Factory;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Notifications;

/// <summary>
/// Watches the factory of every project in the registry for two things that a person wants to hear
/// about, and raises one browser notification for each. The first is an event that jidoka sent: a
/// task or an epic parked, only parked tasks left, the acceptance gate, a stopped factory, a
/// paused one, a permission prompt. The second is a heartbeat that went stale while its epic runs.
/// </summary>
/// <remarks>
/// What stands when the app first reads a project raises nothing, because jidoka told the person
/// already. Each event raises once, and a stale heartbeat warns once for as long as it stays stale;
/// a heartbeat that turns fresh and stale again warns again. The watch follows the same changes of
/// a project as the board does, and checks again on a timer, because a heartbeat is a file that
/// changes nothing under `.beads`.
/// </remarks>
public sealed class FactoryWatch : IDisposable
{
    /// <summary>How often the watch checks every project without a change to prompt it.</summary>
    public static readonly TimeSpan Interval = TimeSpan.FromSeconds(30);

    private readonly FactoryReader reader;
    private readonly ProjectCatalog catalog;
    private readonly BacklogCache backlogs;
    private readonly ProjectWatchers watchers;
    private readonly Heartbeats heartbeats;
    private readonly TimeProvider clock;

    private readonly Lock gate = new();
    private readonly HashSet<ProjectPath> primed = [];
    private readonly HashSet<string> announced = new(StringComparer.Ordinal);
    private readonly HashSet<(ProjectPath Project, string Epic)> stale = [];
    private ITimer? timer;

    public FactoryWatch(
        FactoryReader reader,
        ProjectCatalog catalog,
        BacklogCache backlogs,
        ProjectWatchers watchers,
        Heartbeats heartbeats,
        TimeProvider clock)
    {
        this.reader = reader;
        this.catalog = catalog;
        this.backlogs = backlogs;
        this.watchers = watchers;
        this.heartbeats = heartbeats;
        this.clock = clock;
    }

    /// <summary>Raised once for each notification, on whichever thread found the cause.</summary>
    public event Action<BrowserNotification>? Raised;

    /// <summary>Starts the watch: it checks at once, after each change of a project, and on every interval.</summary>
    public void Start()
    {
        backlogs.Changed += OnChanged;
        timer = clock.CreateTimer(_ => _ = CheckAsync(), null, TimeSpan.Zero, Interval);
    }

    /// <summary>
    /// Checks every project of the registry, and starts the watch on the `.beads` directory of each
    /// one that has none, so that a park is seen even when no page shows that project.
    /// </summary>
    public async Task CheckAsync()
    {
        var projects = catalog.Projects();
        foreach (var project in projects)
        {
            watchers.Watch(project);
        }

        await Task.WhenAll(projects.Select(CheckAsync));
    }

    /// <summary>Checks one project.</summary>
    public async Task CheckAsync(ProjectPath project)
    {
        var factory = await reader.ReadAsync(project);
        foreach (var notification in Take(factory))
        {
            Raised?.Invoke(notification);
        }
    }

    public void Dispose()
    {
        backlogs.Changed -= OnChanged;
        timer?.Dispose();
    }

    private void OnChanged(BacklogChange change)
    {
        if (catalog.Find(change.Project) is not null)
        {
            _ = CheckAsync(change.Project);
        }
    }

    private List<BrowserNotification> Take(FactoryProject factory)
    {
        if (factory.IsUnread)
        {
            return [];
        }

        lock (gate)
        {
            var announce = !primed.Add(factory.Project);
            var raised = new List<BrowserNotification>();
            foreach (var recorded in FactoryEvent.In(factory))
            {
                if (announced.Add(recorded.Key) && announce)
                {
                    raised.Add(recorded.ToBrowserNotification());
                }
            }

            raised.AddRange(WarningsOfStaleHeartbeats(factory, announce));
            return raised;
        }
    }

    private List<BrowserNotification> WarningsOfStaleHeartbeats(FactoryProject factory, bool announce)
    {
        var now = clock.GetUtcNow();
        var staleNow = new Dictionary<(ProjectPath, string), (FactoryEpic Epic, TimeSpan Age)>();
        foreach (var held in factory.Epics.Where(epic => epic.IsRunning))
        {
            if (heartbeats.AgeOf(held.Epic.Id, now) is { } age && Heartbeats.IsStale(age))
            {
                staleNow[(factory.Project, held.Epic.Id)] = (held, age);
            }
        }

        stale.RemoveWhere(spell => spell.Project.Equals(factory.Project) && !staleNow.ContainsKey(spell));
        var warnings = new List<BrowserNotification>();
        foreach (var (spell, (held, age)) in staleNow)
        {
            if (stale.Add(spell) && announce)
            {
                warnings.Add(Warning(factory.Project, held, age, now));
            }
        }

        return warnings;
    }

    private static BrowserNotification Warning(ProjectPath project, FactoryEpic held, TimeSpan age, DateTimeOffset now) =>
        new(
            $"{project.Value}|heartbeat-stale:{held.Epic.Id}|{(now - age).ToUnixTimeSeconds()}",
            $"Heartbeat stale: {held.Epic.Title}",
            $"The last beat was {(long)age.TotalSeconds} seconds ago. The host that runs this epic may have stopped.",
            BeadPageAddress.Of(new BeadAddress(project, held.Epic.Id)));
}
