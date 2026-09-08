namespace TracerUi.Core.Beads;

/// <summary>One action that the UI offers, and the bd command, subcommands and flags that it needs.</summary>
/// <param name="Name">What the person calls this action.</param>
/// <param name="Command">The bd command that the action runs.</param>
/// <param name="Subcommands">The subcommands of that command which the action needs, or none.</param>
/// <param name="Flags">The flags of that command which the action needs, each with its two dashes.</param>
public sealed record UiVerb(
    string Name,
    string Command,
    IReadOnlyList<string> Subcommands,
    IReadOnlyList<string> Flags)
{
    /// <summary>How the doctor page prints this action as a command line.</summary>
    public string CommandLine
    {
        get
        {
            var parts = new List<string> { "bd", Command };
            if (Subcommands.Count > 0)
            {
                parts.Add(string.Join('|', Subcommands));
            }

            parts.AddRange(Flags);
            return string.Join(' ', parts);
        }
    }
}

/// <summary>Every action that the UI offers. The doctor page reports each one against the installed bd.</summary>
public static class UiVerbs
{
    public static UiVerb ListTheBeads { get; } =
        new("List the beads of a project", "list", [], ["--json", "--all"]);

    public static UiVerb ShowOneBead { get; } =
        new("Show one bead", "show", [], ["--json"]);

    public static UiVerb CreateABead { get; } =
        new("Create a bead", "create", [], ["--title", "--type", "--silent"]);

    public static UiVerb CreateInAnEpic { get; } =
        new("Create a bead inside an epic", "create", [], ["--title", "--type", "--parent", "--silent"]);

    public static UiVerb CreateAnEpic { get; } =
        new("Create an epic", "create", [], ["--title", "--type", "--silent"]);

    public static UiVerb MoveIntoAnEpic { get; } =
        new("Move a bead into an epic", "update", [], ["--parent"]);

    public static UiVerb SetThePriority { get; } =
        new("Set the priority of a bead", "update", [], ["--priority"]);

    public static UiVerb SetTheType { get; } =
        new("Set the type of a bead", "update", [], ["--type"]);

    public static UiVerb SetTheStatus { get; } =
        new("Set the status of a bead", "update", [], ["--status"]);

    public static UiVerb EditTheProse { get; } =
        new("Edit the title and the description", "update", [], ["--title", "--description"]);

    public static UiVerb EditTheAcceptanceCriteria { get; } =
        new("Edit the acceptance criteria", "update", [], ["--acceptance"]);

    public static UiVerb RewriteTheNotes { get; } =
        new("Rewrite the notes of a bead", "update", [], ["--notes"]);

    public static UiVerb LabelABead { get; } =
        new("Add and remove a label", "label", ["add", "remove"], []);

    public static UiVerb CloseWithAReason { get; } =
        new("Close a bead with a reason", "close", [], ["--reason"]);

    public static UiVerb DeferABead { get; } =
        new("Defer a bead", "defer", [], []);

    public static UiVerb UndeferABead { get; } =
        new("Undefer a bead", "undefer", [], []);

    public static UiVerb AddAComment { get; } =
        new("Add a comment", "comment", [], []);

    public static UiVerb ReadTheComments { get; } =
        new("Read the comments of a bead", "comments", [], ["--json"]);

    public static UiVerb EditADependencyEdge { get; } =
        new("Add and remove a dependency edge", "dep", ["add", "remove"], []);

    public static IReadOnlyList<UiVerb> All { get; } =
    [
        ListTheBeads,
        ShowOneBead,
        CreateABead,
        CreateInAnEpic,
        CreateAnEpic,
        MoveIntoAnEpic,
        SetThePriority,
        SetTheType,
        SetTheStatus,
        EditTheProse,
        EditTheAcceptanceCriteria,
        RewriteTheNotes,
        LabelABead,
        CloseWithAReason,
        DeferABead,
        UndeferABead,
        AddAComment,
        ReadTheComments,
        EditADependencyEdge,
    ];

    /// <summary>The bd commands that the probe asks about, each one once.</summary>
    public static IReadOnlyList<string> Commands { get; } = [.. All.Select(verb => verb.Command).Distinct()];
}
