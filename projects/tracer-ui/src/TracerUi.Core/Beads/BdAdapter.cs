using System.Collections.Concurrent;
using System.Globalization;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Core.Beads;

/// <summary>The one layer that owns every bd invocation.</summary>
public sealed class BdAdapter
{
    private readonly IBdProcess process;
    private readonly ConcurrentDictionary<ProjectPath, Lazy<Task<BdCapabilities>>> probed = new();
    private readonly Lock gathering = new();
    private readonly HashSet<ProjectPath> gathered = [];
    private int runs;

    public BdAdapter(IBdProcess process)
    {
        this.process = process;
    }

    /// <summary>
    /// Names the project that a write of this app changed. The adapter is the one layer that makes
    /// a write, so a listener that follows this event misses none of them.
    /// </summary>
    public event Action<ProjectPath>? Wrote;

    /// <summary>
    /// Runs many writes and names each project that they changed once, at the end of the run. bd
    /// writes one bead at a time, and a listener that read a project between two of those writes
    /// would show a selection that is half written.
    /// </summary>
    public async Task<T> GatherTheWritesAsync<T>(Func<Task<T>> writes)
    {
        lock (gathering)
        {
            runs++;
        }

        try
        {
            return await writes();
        }
        finally
        {
            foreach (var project in EndOfARun())
            {
                Wrote?.Invoke(project);
            }
        }
    }

    // The projects to name now that a run ended: none while another run is still open, so that two
    // runs at once name each project once between them.
    private IReadOnlyList<ProjectPath> EndOfARun()
    {
        lock (gathering)
        {
            runs--;
            if (runs > 0)
            {
                return [];
            }

            var projects = gathered.ToArray();
            gathered.Clear();
            return projects;
        }
    }

    private void NameTheProjectOrHoldItForTheRun(ProjectPath project)
    {
        lock (gathering)
        {
            if (runs > 0)
            {
                gathered.Add(project);
                return;
            }
        }

        Wrote?.Invoke(project);
    }

    public async Task<BdOutcome> ReadyAsync(ProjectPath project)
    {
        string[] arguments = ["ready", "--json"];
        return OutcomeOf(arguments, await process.RunAsync(project.Value, arguments));
    }

    private static BdOutcome OutcomeOf(IReadOnlyList<string> arguments, BdResult result)
    {
        if (!result.Succeeded)
        {
            return BdOutcome.Failure(BdFailure.Describe(arguments, result));
        }

        return BdJson.TryParse(result.StandardOutput, out var records)
            ? BdOutcome.Answer(records)
            : BdOutcome.Failure(
                $"bd {string.Join(' ', arguments)} answered with something that is not JSON.");
    }

    /// <summary>
    /// Reads every bead of the project, whatever its status. bd list hides the closed beads and
    /// applies a limit by default, so the read asks for every status and lifts the limit. An older
    /// bd has no --all flag, and answers the plain list instead.
    /// </summary>
    public async Task<BdOutcome> ListAsync(ProjectPath project)
    {
        string[] everyStatus = ["list", "--all", "--limit", "0", "--json"];
        var result = await process.RunAsync(project.Value, everyStatus);
        if (result.Succeeded)
        {
            return OutcomeOf(everyStatus, result);
        }

        string[] plain = ["list", "--json"];
        return OutcomeOf(plain, await process.RunAsync(project.Value, plain));
    }

    /// <summary>Reads one bead in full, with the dependency edges that name the beads it depends on.</summary>
    public async Task<BdOutcome> ShowAsync(BeadAddress bead)
    {
        string[] arguments = ["show", bead.Id, "--json"];
        return OutcomeOf(arguments, await process.RunAsync(bead.Project.Value, arguments));
    }

    /// <summary>Reads the comments of one bead, in the order that bd prints them.</summary>
    public async Task<BdOutcome> CommentsAsync(BeadAddress bead)
    {
        string[] arguments = ["comments", bead.Id, "--json"];
        return OutcomeOf(arguments, await process.RunAsync(bead.Project.Value, arguments));
    }

    /// <summary>Reads the beads that bd calls blocked, each with the beads that block it.</summary>
    public async Task<BdOutcome> BlockedAsync(ProjectPath project)
    {
        string[] arguments = ["blocked", "--json"];
        return OutcomeOf(arguments, await process.RunAsync(project.Value, arguments));
    }

    /// <summary>
    /// Adds one comment to a bead. A comment appends, where a write of the notes or the description
    /// replaces what was there, so it loses nothing that another writer left.
    /// </summary>
    public Task<BdWriteOutcome> CommentAsync(BeadAddress bead, string text) =>
        WriteAsync(bead, UiVerbs.AddAComment, ["comment", bead.Id, text]);

    public Task<BdWriteOutcome> AddLabelAsync(BeadAddress bead, BeadLabel label) =>
        WriteAsync(bead, UiVerbs.LabelABead, ["label", "add", bead.Id, label.Word]);

    public Task<BdWriteOutcome> RemoveLabelAsync(BeadAddress bead, BeadLabel label) =>
        WriteAsync(bead, UiVerbs.LabelABead, ["label", "remove", bead.Id, label.Word]);

    /// <summary>Sets the priority of a bead. bd takes a number from 0 to 4, where 0 is the most urgent.</summary>
    public Task<BdWriteOutcome> SetPriorityAsync(BeadAddress bead, long priority) =>
        WriteAsync(
            bead,
            UiVerbs.SetThePriority,
            ["update", bead.Id, "--priority", priority.ToString(CultureInfo.InvariantCulture)]);

    public Task<BdWriteOutcome> SetTypeAsync(BeadAddress bead, BeadTypeWord type) =>
        WriteAsync(bead, UiVerbs.SetTheType, ["update", bead.Id, "--type", type.Word()]);

    /// <summary>Moves a bead into an epic.</summary>
    public Task<BdWriteOutcome> SetParentAsync(BeadAddress bead, string epicId) =>
        WriteAsync(bead, UiVerbs.MoveIntoAnEpic, ["update", bead.Id, "--parent", epicId]);

    /// <summary>
    /// Sets the title and the description of a bead in one write. A bead with no title is
    /// unreadable on the board, so the adapter refuses an empty title and runs nothing.
    /// </summary>
    public Task<BdWriteOutcome> EditProseAsync(BeadAddress bead, string title, string description)
    {
        var newTitle = title.Trim();
        return newTitle.Length == 0
            ? Task.FromResult(BdWriteOutcome.Failure("A bead needs a title."))
            : WriteAsync(
                bead,
                UiVerbs.EditTheProse,
                ["update", bead.Id, "--title", newTitle, "--description", description]);
    }

    /// <summary>
    /// Sets the acceptance criteria of a bead. bd takes them on their own, so this write sends no
    /// other part of the prose and leaves the title, the description and the notes as they were.
    /// </summary>
    public Task<BdWriteOutcome> EditAcceptanceAsync(BeadAddress bead, string acceptance) =>
        WriteAsync(
            bead,
            UiVerbs.EditTheAcceptanceCriteria,
            ["update", bead.Id, "--acceptance", acceptance]);

    /// <summary>
    /// Replaces the notes of a bead with the text that the person wrote. bd keeps no earlier copy of
    /// them, so the UI asks for this write on its own and never folds it into another one.
    /// </summary>
    public Task<BdWriteOutcome> RewriteNotesAsync(BeadAddress bead, string notes) =>
        WriteAsync(bead, UiVerbs.RewriteTheNotes, ["update", bead.Id, "--notes", notes]);

    /// <summary>Adds a blocker to a bead, so that the blocker must close before the bead is ready.</summary>
    public Task<BdWriteOutcome> AddBlockerAsync(BeadAddress bead, string blockerId) =>
        EdgeAsync(bead, blockerId, "add");

    public Task<BdWriteOutcome> RemoveBlockerAsync(BeadAddress bead, string blockerId) =>
        EdgeAsync(bead, blockerId, "remove");

    // Adds or removes one dependency edge. bd names the bead first and its blocker second, so the
    // two subcommands take the same pair in the same order.
    private Task<BdWriteOutcome> EdgeAsync(BeadAddress bead, string blockerId, string subcommand)
    {
        var blocker = blockerId.Trim();
        if (blocker.Length == 0)
        {
            return Task.FromResult(BdWriteOutcome.Failure("An edge needs the blocker at its far end."));
        }

        return string.Equals(blocker, bead.Id, StringComparison.Ordinal)
            ? Task.FromResult(BdWriteOutcome.Failure("A bead cannot block itself."))
            : WriteAsync(bead, UiVerbs.EditADependencyEdge, ["dep", subcommand, bead.Id, blocker]);
    }

    public Task<BdWriteOutcome> SetStatusAsync(BeadAddress bead, StoredStatusWord status) =>
        WriteAsync(bead, UiVerbs.SetTheStatus, ["update", bead.Id, "--status", status.Word()]);

    /// <summary>
    /// Closes a bead with the reason that the person gave. A close without a reason leaves a hole in
    /// the history of the bead, so the adapter refuses it and runs nothing.
    /// </summary>
    public Task<BdWriteOutcome> CloseAsync(BeadAddress bead, string reason) =>
        reason.Trim().Length == 0
            ? Task.FromResult(BdWriteOutcome.Failure(
                "A close needs a reason. The history of this bead is what a later reader has."))
            : WriteAsync(bead, UiVerbs.CloseWithAReason, ["close", bead.Id, "--reason", reason]);

    /// <summary>
    /// Creates a bead from a title, a type and the epic that is to hold it. A null epic leaves the
    /// bead unparented. The create asks bd for the id alone, because the app names the new bead in
    /// the writes that follow.
    /// </summary>
    public async Task<BdCreateOutcome> CreateAsync(
        ProjectPath project,
        string title,
        string type,
        string? epicId)
    {
        var named = title.Trim();
        if (named.Length == 0)
        {
            return BdCreateOutcome.Failure("A bead needs a title.");
        }

        var verb = epicId is null ? UiVerbs.CreateABead : UiVerbs.CreateInAnEpic;
        string[] arguments = epicId is null
            ? ["create", "--title", named, "--type", type, "--silent"]
            : ["create", "--title", named, "--type", type, "--parent", epicId, "--silent"];
        return await MakeAsync(project, verb, arguments);
    }

    /// <summary>
    /// Creates an epic from a title alone, and sets it to in progress at once. An epic that stayed
    /// open would read as ready work, and an epic is a container and never work of its own.
    /// </summary>
    public async Task<BdCreateOutcome> CreateEpicAsync(ProjectPath project, string title)
    {
        var named = title.Trim();
        if (named.Length == 0)
        {
            return BdCreateOutcome.Failure("An epic needs a title.");
        }

        string[] arguments = ["create", "--title", named, "--type", "epic", "--silent"];
        var made = await MakeAsync(project, UiVerbs.CreateAnEpic, arguments);
        if (!made.Created)
        {
            return made;
        }

        var started = await SetStatusAsync(new BeadAddress(project, made.Id), StoredStatusWord.InProgress);
        return started.Wrote
            ? made
            : BdCreateOutcome.MadeButNotStarted(
                made.Id,
                $"bd made the epic {made.Id}, but it is still open. {started.Message}");
    }

    private async Task<BdCreateOutcome> MakeAsync(
        ProjectPath project,
        UiVerb verb,
        IReadOnlyList<string> arguments)
    {
        var capabilities = await CapabilitiesAsync(project);
        var missing = capabilities.MissingCapability(verb);
        if (missing.Length > 0)
        {
            return BdCreateOutcome.Failure(missing);
        }

        var result = await process.RunAsync(project.Value, arguments);
        if (!result.Succeeded)
        {
            return BdCreateOutcome.Failure(BdFailure.Describe(arguments, result));
        }

        NameTheProjectOrHoldItForTheRun(project);
        var id = result.StandardOutput.Trim();
        return id.Length > 0
            ? BdCreateOutcome.Made(id)
            : BdCreateOutcome.Failure("bd made a bead but printed no id for it.");
    }

    /// <summary>
    /// Defers a bead without naming a date. bd takes one on --until, and this write sends none, so
    /// a person who wants a date runs bd itself.
    /// </summary>
    public Task<BdWriteOutcome> DeferAsync(BeadAddress bead) =>
        WriteAsync(bead, UiVerbs.DeferABead, ["defer", bead.Id]);

    // Runs one write, after the capabilities say that this bd offers it. The check is the same one
    // that disables the button, so a write that slips past the UI still fails as a message.
    private async Task<BdWriteOutcome> WriteAsync(
        BeadAddress bead,
        UiVerb verb,
        IReadOnlyList<string> arguments)
    {
        var capabilities = await CapabilitiesAsync(bead.Project);
        var missing = capabilities.MissingCapability(verb);
        if (missing.Length > 0)
        {
            return BdWriteOutcome.Failure(missing);
        }

        var result = await process.RunAsync(bead.Project.Value, arguments);
        if (!result.Succeeded)
        {
            return BdWriteOutcome.Failure(BdFailure.Describe(arguments, result));
        }

        NameTheProjectOrHoldItForTheRun(bead.Project);
        return BdWriteOutcome.Written();
    }

    /// <summary>Probes the installed bd for this project. The answer holds for the life of the app.</summary>
    public Task<BdCapabilities> CapabilitiesAsync(ProjectPath project) =>
        // The Lazy is what holds the probe to one run. GetOrAdd may run its factory on more than one
        // thread and keep only the first answer, so without it two callers that arrive together each
        // launch a whole probe, which is a bd process per command the probe asks about.
        probed.GetOrAdd(project, path => new Lazy<Task<BdCapabilities>>(() => ProbeAsync(path))).Value;

    private async Task<BdCapabilities> ProbeAsync(ProjectPath project)
    {
        var version = await process.RunAsync(project.Value, ["version"]);
        var help = await process.RunAsync(project.Value, ["--help"]);

        var commandHelp = new Dictionary<string, BdResult>(StringComparer.Ordinal);
        foreach (var command in UiVerbs.Commands)
        {
            commandHelp[command] = await process.RunAsync(project.Value, [command, "--help"]);
        }

        var beads = await SampleAsync(project);
        var comments = await CommentsOfOneBeadAsync(project, beads);
        return CapabilityProbe.From(version, help, commandHelp, beads, comments);
    }

    // Reads the comments of one sampled bead, to learn the names that this bd gives a comment.
    // A bead in the sample carries no comment, so the probe asks for them on their own.
    private async Task<BdComments> CommentsOfOneBeadAsync(
        ProjectPath project,
        IReadOnlyList<BeadRecord> sample)
    {
        var identifier = IdOfTheBeadWithTheMostComments(sample);
        if (identifier.Length == 0)
        {
            return BdComments.Unread("This project has no bead, so the probe read no comment.");
        }

        var outcome = await CommentsAsync(new BeadAddress(project, identifier));
        if (!outcome.Answered)
        {
            return BdComments.Unread(outcome.Message);
        }

        if (outcome.Records.Count == 0)
        {
            return BdComments.Unread($"Bead {identifier} has no comment, so the probe read no name.");
        }

        return new BdComments(BeadFields.ResolveCommentsFrom(outcome.Records), string.Empty);
    }

    // Reads a sample of beads for the probe. bd omits a field from its JSON when no bead in the
    // sample sets it, so the probe reads every bead of the project.
    private async Task<IReadOnlyList<BeadRecord>> SampleAsync(ProjectPath project) =>
        (await ListAsync(project)).Records;

    // A bead with no comment teaches the probe no name, so the most commented bead wins.
    private static string IdOfTheBeadWithTheMostComments(IReadOnlyList<BeadRecord> sample) =>
        sample
            .Where(bead => bead.Text(BeadFields.IdNames).Length > 0)
            .OrderByDescending(bead => bead.Number(BeadFields.CommentCountNames, 0))
            .Select(bead => bead.Text(BeadFields.IdNames))
            .FirstOrDefault(string.Empty);
}
