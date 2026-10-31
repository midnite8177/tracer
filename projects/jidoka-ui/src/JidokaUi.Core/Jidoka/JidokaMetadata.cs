using System.Text.Json;
using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;

namespace JidokaUi.Core.Jidoka;

/// <summary>The lap of a task as jidoka's scheduler wrote it, each part as text and empty when jidoka wrote none.</summary>
/// <param name="Number">The number of the lap.</param>
/// <param name="Stage">The stage the lap stands at.</param>
/// <param name="TriesAtStage">The tries the lap used at its stage, which the merge counts apart from every other stage.</param>
/// <param name="CapAtStage">The tries jidoka lets the lap use at its stage.</param>
public sealed record RecordedLap(string Number, string Stage, string TriesAtStage, string CapAtStage);

/// <summary>Whether an epic waits at the acceptance gate, as the gate script recorded it.</summary>
public enum GateState
{
    /// <summary>The epic records no gate state, or one other than waiting.</summary>
    NotWaiting,

    /// <summary>The epic waits on the human's decision at the gate.</summary>
    Waiting,
}

/// <summary>One entry of the record that jidoka's notify script keeps on an epic.</summary>
/// <param name="Name">The event, as jidoka names it.</param>
/// <param name="BeadId">The bead the event points at.</param>
/// <param name="Fingerprint">The state that the event announced.</param>
/// <param name="Title">The headline jidoka gave the notification, with the title of the bead in it.</param>
/// <param name="Text">The sentence jidoka gave the notification, or empty when it gave none.</param>
public sealed record RecordedEvent(string Name, string BeadId, string Fingerprint, string Title, string Text);

/// <summary>
/// The one module that spells the metadata keys jidoka writes on a bead and the shape of each
/// value. jidoka owns the keys and the app only reads them, so a rename on jidoka's side edits
/// this file and no other. A caller asks for a question, a lap, a gate state or the recorded
/// events, and never for a key.
/// </summary>
public static class JidokaMetadata
{
    private const string OptionsKey = "question.options";
    private const string RecommendedKey = "question.recommended";
    private const string LapNumberKey = "lap.number";
    private const string LapStageKey = "lap.stage";
    private const string MergeStage = "merge";
    private const string LapTriesKey = "lap.tries";
    private const string LapMergeTriesKey = "lap.mergetries";
    private const string LapTryCapKey = "lap.trycap";
    private const string LapMergeTryCapKey = "lap.mergetrycap";
    private const string GateKey = "gate.state";
    private const string WaitingAtTheGate = "waiting";
    private const string NotificationKey = "notification";

    /// <summary>
    /// The question that jidoka asked on this bead, or null when it asked none. Options that are not
    /// a JSON array of objects with a name make no question, because a panel cannot draw an answer
    /// it cannot name.
    /// </summary>
    public static BeadQuestion? QuestionOn(Bead bead)
    {
        if (!bead.Metadata.TryGetValue(OptionsKey, out var written))
        {
            return null;
        }

        var options = OptionsIn(written);
        return options.Count == 0
            ? null
            : new BeadQuestion(options, bead.Metadata.GetValueOrDefault(RecommendedKey, string.Empty));
    }

    /// <summary>The lap that jidoka's scheduler recorded on this task.</summary>
    public static RecordedLap LapOn(Bead task)
    {
        var stage = Entry(task, LapStageKey);
        var merging = stage == MergeStage;
        return new RecordedLap(
            Entry(task, LapNumberKey),
            stage,
            Entry(task, merging ? LapMergeTriesKey : LapTriesKey),
            Entry(task, merging ? LapMergeTryCapKey : LapTryCapKey));
    }

    /// <summary>Whether this epic waits at the acceptance gate.</summary>
    public static GateState GateStateOn(Bead epic) =>
        Entry(epic, GateKey) == WaitingAtTheGate ? GateState.Waiting : GateState.NotWaiting;

    /// <summary>
    /// The events that jidoka's notify script recorded on this epic. The record maps `event:bead` to an
    /// object with the fingerprint, the title and the text of the notification. An entry whose name does
    /// not split into an event and a bead, or that is no object with a fingerprint and a title, is left out.
    /// </summary>
    public static IReadOnlyList<RecordedEvent> EventsOn(Bead epic)
    {
        if (!epic.Metadata.TryGetValue(NotificationKey, out var text))
        {
            return [];
        }

        using var record = ParseAs(text, JsonValueKind.Object);
        if (record is null)
        {
            return [];
        }

        return
        [
            .. record.RootElement.EnumerateObject()
                .Select(member => EventOf(member.Name, member.Value))
                .OfType<RecordedEvent>(),
        ];
    }

    private static RecordedEvent? EventOf(string name, JsonElement entry)
    {
        var colon = name.IndexOf(':', StringComparison.Ordinal);
        if (colon <= 0 || colon == name.Length - 1 || entry.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        var fingerprint = Field(entry, "fingerprint");
        var title = Field(entry, "title");
        return fingerprint.Length == 0 || title.Length == 0
            ? null
            : new RecordedEvent(name[..colon], name[(colon + 1)..], fingerprint, title, Field(entry, "text"));
    }

    private static string Field(JsonElement entry, string name) =>
        entry.TryGetProperty(name, out var value) ? JsonText.Of(value) : string.Empty;

    private static string Entry(Bead bead, string key) =>
        bead.Metadata.TryGetValue(key, out var value) ? value : string.Empty;

    private static IReadOnlyList<QuestionOption> OptionsIn(string written)
    {
        using var document = ParseAs(written, JsonValueKind.Array);
        return document is null
            ? []
            : [.. document.RootElement.EnumerateArray().Select(OptionOf).OfType<QuestionOption>()];
    }

    private static QuestionOption? OptionOf(JsonElement element)
    {
        if (element.ValueKind != JsonValueKind.Object
            || !element.TryGetProperty("name", out var name)
            || name.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(name.GetString()))
        {
            return null;
        }

        int? confidence = element.TryGetProperty("confidence", out var sure) && sure.TryGetInt32(out var percent)
            ? percent
            : null;
        return new QuestionOption(name.GetString() ?? string.Empty, confidence);
    }

    private static JsonDocument? ParseAs(string text, JsonValueKind kind)
    {
        try
        {
            var document = JsonDocument.Parse(text);
            if (document.RootElement.ValueKind == kind)
            {
                return document;
            }

            document.Dispose();
            return null;
        }
        catch (JsonException)
        {
            return null;
        }
    }
}
