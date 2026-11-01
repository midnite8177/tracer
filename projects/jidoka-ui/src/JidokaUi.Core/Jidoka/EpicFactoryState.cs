namespace JidokaUi.Core.Jidoka;

/// <summary>
/// Whether anything drives an epic, as jidoka's state script works it out from the heartbeat, the
/// watcher and the human label. It is not <see cref="JidokaUi.Core.Factory.EpicState"/>, which reads
/// only the epic's own labels and metadata.
/// </summary>
public enum FactoryState
{
    /// <summary>A manager works the epic, and nothing is left for the person.</summary>
    Running,

    /// <summary>A manager's watcher waits, and the factory carries on by itself.</summary>
    Waiting,

    /// <summary>
    /// The epic or a task of it carries the human label. Whether the answer wakes the factory by itself,
    /// or the person runs the slash command afterwards, is in the next step.
    /// </summary>
    WaitingOnYou,

    /// <summary>No manager runs the epic, and only the person starts it again.</summary>
    Stopped,
}

/// <summary>The words with which the factory view names a <see cref="FactoryState"/>.</summary>
public static class FactoryStates
{
    /// <summary>The state as a person reads it.</summary>
    public static string Words(this FactoryState state) => state switch
    {
        FactoryState.Running => "running",
        FactoryState.Waiting => "waiting",
        FactoryState.WaitingOnYou => "waiting on you",
        FactoryState.Stopped => "stopped",
        _ => throw new ArgumentOutOfRangeException(nameof(state), state, "A factory state is one of four cases."),
    };

    /// <summary>The state as the state script prints it, or null for a word the script does not print.</summary>
    public static FactoryState? Named(string printed) => printed switch
    {
        "running" => FactoryState.Running,
        "waiting" => FactoryState.Waiting,
        "waiting-on-you" => FactoryState.WaitingOnYou,
        "stopped" => FactoryState.Stopped,
        _ => null,
    };
}

/// <summary>The one thing that the person can do for an epic, in the words that jidoka's state script wrote.</summary>
/// <param name="Text">The step in words.</param>
/// <param name="Command">The slash command that the step ends with running, or null when it runs none.</param>
public sealed record NextStep(string Text, string? Command);

/// <summary>One epic's factory state and next step, as jidoka's state script prints them.</summary>
/// <param name="Epic">The id of the epic.</param>
/// <param name="State">What drives the epic.</param>
/// <param name="NextStep">The one thing the person can do for the epic.</param>
/// <param name="WaitingOn">
/// The ids of the beads that carry the human label and so wait on the person, the epic first when it
/// is one of them, and each open task after it.
/// </param>
public sealed record EpicFactoryState(string Epic, FactoryState State, NextStep NextStep, IReadOnlyList<string> WaitingOn);
