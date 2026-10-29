using JidokaUi.Core.Boards;

namespace JidokaUi.Core.Factory;

/// <summary>Where the lap of a task stands, apart from the words that a person reads for it.</summary>
public enum TaskOutcome
{
    /// <summary>The task is open and never held a lap.</summary>
    NoLapYet,

    /// <summary>The task is open and holds a lap at some stage.</summary>
    InLap,

    /// <summary>The task is closed and held a lap, so its lap ended at the merge gate.</summary>
    Merged,

    /// <summary>The task is closed and never held a lap.</summary>
    Closed,
}

/// <summary>
/// One task of an epic that the factory holds, as its lap is recorded in the metadata of the task.
/// Lap, Stage and Tries are the text that a person reads, because the factory writes the lap and the
/// app only shows it. The outcome is what code asks, so that no code compares those words.
/// </summary>
/// <param name="Lap">The number of the lap, or a dash when the task never held one.</param>
/// <param name="Outcome">Where the lap stands.</param>
/// <param name="Stage">The stage of the lap, merged for a closed task that held a lap, or no lap yet.</param>
/// <param name="Tries">The tries the lap used against the cap of its stage, or a dash for a task at rest.</param>
public sealed record TaskLap(string Id, string Title, string Lap, TaskOutcome Outcome, string Stage, string Tries)
{
    private const string NoValue = "-";
    private const string MergeStage = "merge";
    private const int TryCap = 3;
    private const int MergeTryCap = 2;

    /// <summary>True when the task is closed and held a lap, so its lap ended at the merge gate.</summary>
    public bool IsMerged => Outcome == TaskOutcome.Merged;

    /// <summary>The lap of this task, read from the metadata keys that jidoka's scheduler writes.</summary>
    public static TaskLap Of(Bead task)
    {
        var stage = Entry(task, "lap.stage");
        var number = Entry(task, "lap.number");
        var lap = number.Length > 0 ? number : NoValue;
        if (task.IsClosed)
        {
            return stage.Length > 0
                ? new TaskLap(task.Id, task.Title, lap, TaskOutcome.Merged, "merged", NoValue)
                : new TaskLap(task.Id, task.Title, lap, TaskOutcome.Closed, "closed", NoValue);
        }

        if (stage.Length == 0)
        {
            return new TaskLap(task.Id, task.Title, NoValue, TaskOutcome.NoLapYet, "no lap yet", NoValue);
        }

        return new TaskLap(task.Id, task.Title, lap, TaskOutcome.InLap, stage, TriesOf(task, stage));
    }

    private static string TriesOf(Bead task, string stage)
    {
        var merging = stage == MergeStage;
        var used = Entry(task, merging ? "lap.mergetries" : "lap.tries");
        return $"{(used.Length > 0 ? used : "0")}/{(merging ? MergeTryCap : TryCap)}";
    }

    private static string Entry(Bead task, string key) =>
        task.Metadata.TryGetValue(key, out var value) ? value : string.Empty;
}

/// <summary>
/// An epic that carries the factory label, with the lap of each task it holds. The state is what
/// holds the epic: running, parked on a person, or at the acceptance gate. A closed epic answers too,
/// and <see cref="FactoryReader"/> keeps only the open ones.
/// </summary>
public sealed record FactoryEpic(Bead Epic, EpicState State, IReadOnlyList<TaskLap> Tasks)
{
    /// <summary>The label with which jidoka's handoff marks an epic that the factory holds.</summary>
    public const string FactoryLabel = "factory";

    private const string GateKey = "gate.state";
    private const string WaitingAtTheGate = "waiting";

    /// <summary>True while the epic is open and waits on the human's decision at the acceptance gate.</summary>
    public bool AtTheGate => !Epic.IsClosed && State == EpicState.AtTheGate;

    /// <summary>True when neither a person nor the acceptance gate holds the epic, so a manager runs it.</summary>
    public bool IsRunning => State == EpicState.Running;

    /// <summary>
    /// The epic as the factory holds it, or null when this bead is no epic with the factory label.
    /// A closed epic still answers, so that the page of an accepted epic keeps its table. The tasks
    /// are the beads it holds that are not epics, by id.
    /// </summary>
    public static FactoryEpic? Of(Backlog backlog, Bead epic)
    {
        if (!IsFactoryEpic(epic))
        {
            return null;
        }

        var tasks = backlog.Beads
            .Where(bead => !bead.IsEpic && string.Equals(bead.ParentId, epic.Id, StringComparison.Ordinal))
            .OrderBy(bead => bead.Id, StringComparer.Ordinal)
            .Select(TaskLap.Of);
        return new FactoryEpic(epic, StateOf(epic), [.. tasks]);
    }

    /// <summary>
    /// True when this bead is an open epic with the factory label that waits at the acceptance gate.
    /// It answers from the bead alone, for a page that holds no backlog.
    /// </summary>
    public static bool WaitsAtTheGate(Bead epic) =>
        IsFactoryEpic(epic) && !epic.IsClosed && StateOf(epic) == EpicState.AtTheGate;

    /// <summary>
    /// True when this bead is an open epic with the factory label, so jidoka's factory rules apply to it.
    /// It answers from the bead alone, for a page that holds no backlog.
    /// </summary>
    public static bool TakesRules(Bead epic) => IsFactoryEpic(epic) && !epic.IsClosed;

    private static bool IsFactoryEpic(Bead epic) =>
        epic.IsEpic && epic.Labels.Contains(FactoryLabel, StringComparer.OrdinalIgnoreCase);

    private static EpicState StateOf(Bead epic)
    {
        if (epic.Metadata.TryGetValue(GateKey, out var gate) && gate == WaitingAtTheGate)
        {
            return EpicState.AtTheGate;
        }

        return epic.NeedsYou ? EpicState.Parked : EpicState.Running;
    }
}

/// <summary>What holds an epic that the factory holds.</summary>
public enum EpicState
{
    /// <summary>Neither a person nor the acceptance gate holds the epic, so a manager runs it.</summary>
    Running,

    /// <summary>The epic carries the human label and waits on a person.</summary>
    Parked,

    /// <summary>The epic waits on the human's decision at the acceptance gate.</summary>
    AtTheGate,
}

/// <summary>The words with which the factory view names the state of an epic.</summary>
public static class EpicStates
{
    /// <summary>The state as a person reads it.</summary>
    public static string Words(this EpicState state) => state switch
    {
        EpicState.Running => "running",
        EpicState.Parked => "parked",
        EpicState.AtTheGate => "at the acceptance gate",
        _ => throw new ArgumentOutOfRangeException(nameof(state), state, "An epic state is one of three cases."),
    };
}
