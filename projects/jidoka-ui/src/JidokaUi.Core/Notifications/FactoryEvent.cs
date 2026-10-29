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
/// unchanged one is the event the app already knows. The record holds the words of the
/// notification too, so the app shows them and words nothing itself.
/// </summary>
/// <param name="Project">The project whose epic holds the record.</param>
/// <param name="Recorded">The entry of the record, with the event, the bead, the fingerprint and the words.</param>
public sealed record FactoryEvent(ProjectPath Project, RecordedEvent Recorded)
{
    /// <summary>Tells one event of one project from every other, and one state of it from the next.</summary>
    public string Key => $"{Project.Value}|{Recorded.Name}:{Recorded.BeadId}|{Recorded.Fingerprint}";

    /// <summary>The browser notification that announces this event.</summary>
    public BrowserNotification ToBrowserNotification() => new(
        Key,
        Recorded.Title,
        Recorded.Text,
        BeadPageAddress.Of(new BeadAddress(Project, Recorded.BeadId)));

    /// <summary>The events that jidoka recorded on the epics of one project.</summary>
    public static IReadOnlyList<FactoryEvent> In(FactoryProject read) =>
        [.. read.Epics.SelectMany(epic => RecordedOn(read.Project, epic))];

    private static IEnumerable<FactoryEvent> RecordedOn(ProjectPath project, FactoryEpic held) =>
        JidokaMetadata.EventsOn(held.Epic).Select(recorded => new FactoryEvent(project, recorded));
}
