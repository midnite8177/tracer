using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Factory;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Projects;

namespace JidokaUi.Core.Notifications;

/// <summary>
/// One notification that jidoka sent about an epic of the factory, read from the record that
/// jidoka's notify script keeps on the epic. That record maps `event:bead` to a fingerprint of
/// the state it announced, so a new fingerprint under the same name is a new event, and an
/// unchanged one is the event the app already knows.
/// </summary>
/// <param name="Name">The event, as jidoka names it: task-parked, acceptance-gate and the others.</param>
/// <param name="BeadId">The bead the event points at.</param>
/// <param name="Fingerprint">The state that the event announced.</param>
/// <param name="BeadTitle">The title of the bead the event points at, or its id when the epic does not hold it.</param>
public sealed record FactoryEvent(
    ProjectPath Project,
    string EpicId,
    string EpicTitle,
    string Name,
    string BeadId,
    string Fingerprint,
    string BeadTitle)
{
    private const string TaskParked = "task-parked";
    private const string EpicParked = "epic-parked";
    private const string OnlyParkedLeft = "only-parked-left";
    private const string AcceptanceGate = "acceptance-gate";
    private const string FactoryStopped = "factory-stopped";
    private const string FactoryPaused = "factory-paused";
    private const string PermissionPrompt = "permission-prompt";

    private static readonly Dictionary<string, EventWords> Words = new(StringComparer.Ordinal)
    {
        [TaskParked] = new("Task parked", "The task waits on you."),
        [EpicParked] = new("Epic parked", "The epic waits on you."),
        [OnlyParkedLeft] = new("Only parked tasks left", "Every open task of the epic waits on you."),
        [AcceptanceGate] = new(
            "Ready for acceptance",
            "The factory has finished its work on the epic. Merge it, send it back or drop it."),
        [FactoryStopped] = new(
            "Factory stopped",
            "The epic has open tasks and no manager runs it. Start the factory again to carry on."),
        [FactoryPaused] = new("Factory paused", "The factory is paused on a problem that waits on you."),
        [PermissionPrompt] = new("Permission prompt", "The host asks you for a permission while the epic runs."),
    };

    /// <summary>Tells one event of one project from every other, and one state of it from the next.</summary>
    public string Key => $"{Project.Value}|{Name}:{BeadId}|{Fingerprint}";

    /// <summary>The browser notification that announces this event.</summary>
    public BrowserNotification ToBrowserNotification() => new(
        Key,
        $"{Headline}: {(Name == TaskParked ? BeadTitle : EpicTitle)}",
        Sentence,
        BeadPageAddress.Of(new BeadAddress(Project, BeadId)));

    /// <summary>The events that jidoka recorded on the epics of one project.</summary>
    public static IReadOnlyList<FactoryEvent> In(FactoryProject read) =>
        [.. read.Epics.SelectMany(epic => RecordedOn(read.Project, epic))];

    private static IEnumerable<FactoryEvent> RecordedOn(ProjectPath project, FactoryEpic held)
    {
        foreach (var recorded in JidokaMetadata.EventsOn(held.Epic))
        {
            var task = held.Tasks.FirstOrDefault(candidate => candidate.Id == recorded.BeadId);
            yield return new FactoryEvent(
                project,
                held.Epic.Id,
                held.Epic.Title,
                recorded.Name,
                recorded.BeadId,
                recorded.Fingerprint,
                task?.Title ?? recorded.BeadId);
        }
    }

    private string Headline => Words.TryGetValue(Name, out var known) ? known.Headline : Name;

    private string Sentence => Words.TryGetValue(Name, out var known) ? known.Sentence : "The factory waits on you.";

    private sealed record EventWords(string Headline, string Sentence);
}
