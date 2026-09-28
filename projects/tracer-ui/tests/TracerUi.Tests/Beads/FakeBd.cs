using TracerUi.Core.Beads;

namespace TracerUi.Tests.Beads;

/// <summary>
/// A bd that gives scripted stdout and stderr, so that a test fixes one version shape. It can also
/// hold one command line open, in every directory, in one, or one run at a time, so that a test
/// renders a component while that run is still going, and tell a test when a run held in one
/// directory begins.
/// </summary>
public sealed class FakeBd : IBdProcess
{
    private readonly Dictionary<string, Task<BdResult>> scripted = new(StringComparer.Ordinal);

    private readonly Dictionary<Run, BdResult> scriptedPerDirectory = [];
    private readonly List<Run> runs = [];
    private readonly Dictionary<string, Action<FakeBd>> changes = new(StringComparer.Ordinal);
    private readonly Dictionary<string, TaskCompletionSource<BdResult>> held = new(StringComparer.Ordinal);
    private readonly Dictionary<Run, HeldRun> heldPerDirectory = [];
    private readonly Dictionary<string, Queue<OneHeldRun>> heldOneAtATime = new(StringComparer.Ordinal);

    /// <summary>The command lines that the code under test ran, in order.</summary>
    public List<string> Invocations { get; } = [];

    /// <summary>How many times the code under test ran this command line in this directory.</summary>
    public int Runs(string workingDirectory, string commandLine) =>
        runs.Count(new Run(workingDirectory, commandLine).Equals);

    /// <summary>A bd that answers the read which the add-project flow makes, and nothing else.</summary>
    public static FakeBd ThatAnswersReady() => new FakeBd().Prints("ready --json", "[]");

    /// <summary>
    /// Scripts the help of a bd that offers every write the UI makes, so that a probe of it finds
    /// each command, subcommand and flag that a write of one bead, or a create, needs.
    /// </summary>
    public FakeBd DeclaresEveryWrite() =>
        Prints("version", "bd version 1.2.2")
            .Prints("--help", """
                Working With Issues:
                  close             Close one or more issues
                  comment           Add a comment to an issue
                  create            Create a new issue
                  defer             Defer one or more issues for later
                  dep               Manage dependencies
                  label             Manage issue labels
                  update            Update one or more issues
                """)
            .Prints("create --help", """
                Flags:
                      --parent string   Parent issue ID for hierarchical child
                      --silent          Output only the issue ID (for scripting)
                      --title string    Issue title
                  -t, --type string     Issue type
                """)
            .Prints("dep --help", """
                Available Commands:
                  add       Add a dependency
                  remove    Remove a dependency
                """)
            .Prints("close --help", """
                Flags:
                  -r, --reason string   Reason for closing
                """)
            .Prints("comment --help", """
                Flags:
                      --stdin   Read comment text from stdin
                """)
            .Prints("defer --help", """
                Flags:
                      --until string   Defer until a specific time
                """)
            .Prints("label --help", """
                Available Commands:
                  add       Add a label to one or more issues
                  remove    Remove a label from one or more issues
                """)
            .Prints("update --help", """
                Flags:
                      --acceptance string      Acceptance criteria
                      --add-label strings      Add labels
                  -d, --description string     Issue description
                      --notes string           Additional notes
                      --parent string          The epic that holds this issue
                  -p, --priority string        Priority
                      --remove-label strings   Remove labels
                  -s, --status string          New status
                      --title string           New title
                  -t, --type string            New type
                """);

    /// <summary>
    /// Makes this bd answer differently once one command line ran, as a write changes the bead that
    /// a later read gives back.
    /// </summary>
    public FakeBd After(string commandLine, Action<FakeBd> change)
    {
        changes[commandLine] = change;
        return this;
    }

    public FakeBd Prints(string commandLine, string standardOutput)
    {
        scripted[commandLine] = Task.FromResult(new BdResult(0, standardOutput, string.Empty));
        return this;
    }

    /// <summary>
    /// Scripts the answer that this bd gives one command line in one directory alone, so that a test
    /// fixes a different shape per project.
    /// </summary>
    public FakeBd PrintsIn(string workingDirectory, string commandLine, string standardOutput)
    {
        scriptedPerDirectory[new Run(workingDirectory, commandLine)] = new BdResult(0, standardOutput, string.Empty);
        return this;
    }

    public FakeBd Fails(string commandLine, string standardError)
    {
        scripted[commandLine] = Task.FromResult(new BdResult(1, string.Empty, standardError));
        return this;
    }

    /// <summary>
    /// Makes every run of this command line throw this exception. A later <see cref="Prints"/> or
    /// <see cref="Fails"/> of the same command line replaces it.
    /// </summary>
    public FakeBd Throws(string commandLine, Exception exception)
    {
        scripted[commandLine] = Task.FromException<BdResult>(exception);
        return this;
    }

    /// <summary>
    /// Holds every run of this command line open until <see cref="Answers"/>, so that a test renders a
    /// component while bd has not answered yet. Every held run gets the same answer.
    /// </summary>
    public FakeBd Holds(string commandLine)
    {
        held[commandLine] = new TaskCompletionSource<BdResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        return this;
    }

    /// <summary>
    /// Answers a run that <see cref="Holds"/> is holding open, as bd itself would have, and lets a
    /// later run of the same command line fall through to what it is otherwise scripted to answer.
    /// </summary>
    public FakeBd Answers(string commandLine, string standardOutput)
    {
        if (!held.Remove(commandLine, out var holding))
        {
            throw new InvalidOperationException(
                $"\"{commandLine}\" is not a held run. Call Holds before Answers.");
        }

        Release(holding, commandLine, standardOutput);
        return this;
    }

    /// <summary>
    /// Holds every run of this command line in one directory open until <see cref="AnswersIn"/>
    /// answers it or <see cref="ThrowsIn"/> fails it, so that a test keeps the read of one project
    /// waiting while the same command line answers in another. It wins over a <see cref="Holds"/>
    /// of the same command line.
    /// </summary>
    public FakeBd HoldsIn(string workingDirectory, string commandLine)
    {
        heldPerDirectory[new Run(workingDirectory, commandLine)] = new HeldRun(
            new TaskCompletionSource<BdResult>(TaskCreationOptions.RunContinuationsAsynchronously),
            new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously));
        return this;
    }

    /// <summary>
    /// A task that completes when a run that <see cref="HoldsIn"/> holds open in this directory
    /// begins, so that a test waits for the code under test to reach bd even when no render follows.
    /// Ask for it before <see cref="AnswersIn"/> answers that run or <see cref="ThrowsIn"/> fails it.
    /// </summary>
    public Task StartsIn(string workingDirectory, string commandLine) =>
        HeldIn(new Run(workingDirectory, commandLine), nameof(StartsIn)).Started.Task;

    /// <summary>
    /// Answers a run that <see cref="HoldsIn"/> is holding open in this directory, as bd itself would
    /// have, and lets a later run there fall through to what it is otherwise scripted to answer.
    /// </summary>
    public FakeBd AnswersIn(string workingDirectory, string commandLine, string standardOutput)
    {
        var holding = TakeHeldIn(workingDirectory, commandLine, nameof(AnswersIn));
        Release(holding.Answer, commandLine, standardOutput);
        return this;
    }

    /// <summary>
    /// Makes the run that <see cref="HoldsIn"/> holds open in this directory throw an
    /// <see cref="InvalidOperationException"/> with this message instead of answering. A later run
    /// there answers what it is otherwise scripted to answer.
    /// </summary>
    public FakeBd ThrowsIn(string workingDirectory, string commandLine, string message)
    {
        var holding = TakeHeldIn(workingDirectory, commandLine, nameof(ThrowsIn));
        holding.Answer.SetException(new InvalidOperationException(message));
        return this;
    }

    /// <summary>
    /// Holds the next run of this command line open on its own, and gives that run to answer. Each
    /// call holds one more run, in the order the runs begin, so that a test answers two runs of one
    /// command line in the order it picks. It wins over a <see cref="Holds"/> of the same command
    /// line.
    /// </summary>
    public OneHeldRun HoldsTheNextRun(string commandLine)
    {
        var run = new OneHeldRun(this, commandLine);
        if (!heldOneAtATime.TryGetValue(commandLine, out var waiting))
        {
            waiting = new Queue<OneHeldRun>();
            heldOneAtATime[commandLine] = waiting;
        }

        waiting.Enqueue(run);
        return run;
    }

    private HeldRun TakeHeldIn(string workingDirectory, string commandLine, string caller)
    {
        var run = new Run(workingDirectory, commandLine);
        var holding = HeldIn(run, caller);
        heldPerDirectory.Remove(run);
        return holding;
    }

    private HeldRun HeldIn(Run run, string caller) =>
        heldPerDirectory.TryGetValue(run, out var holding)
            ? holding
            : throw new InvalidOperationException(
                $"\"{run.CommandLine}\" in {run.Directory} is not a held run. Call HoldsIn before {caller}.");

    private void Release(TaskCompletionSource<BdResult> holding, string commandLine, string standardOutput)
    {
        if (changes.TryGetValue(commandLine, out var change))
        {
            change(this);
        }

        holding.SetResult(new BdResult(0, standardOutput, string.Empty));
    }

    public Task<BdResult> RunAsync(string workingDirectory, IReadOnlyList<string> arguments)
    {
        var commandLine = string.Join(' ', arguments);
        Invocations.Add(commandLine);
        var run = new Run(workingDirectory, commandLine);
        runs.Add(run);
        if (heldPerDirectory.TryGetValue(run, out var holdingHere))
        {
            holdingHere.Started.TrySetResult();
            return holdingHere.Answer.Task;
        }

        if (heldOneAtATime.TryGetValue(commandLine, out var waiting) && waiting.TryDequeue(out var next))
        {
            return next.Answer.Task;
        }

        if (held.TryGetValue(commandLine, out var holding))
        {
            return holding.Task;
        }

        var answer = Answer(run, arguments[0]);
        if (changes.TryGetValue(commandLine, out var change))
        {
            change(this);
        }

        return answer;
    }

    // The scripted answer for this directory, or the one that every directory shares, or the
    // failure that a bd gives a command it does not have.
    private Task<BdResult> Answer(Run run, string verb)
    {
        if (scriptedPerDirectory.TryGetValue(run, out var here))
        {
            return Task.FromResult(here);
        }

        return scripted.TryGetValue(run.CommandLine, out var anywhere)
            ? anywhere
            : Task.FromResult(new BdResult(1, string.Empty, $"unknown command \"{verb}\" for \"bd\""));
    }

    private sealed record Run(string Directory, string CommandLine);

    /// <summary>One run that <see cref="HoldsTheNextRun"/> holds open until a test answers it.</summary>
    public sealed class OneHeldRun
    {
        private readonly FakeBd bd;
        private readonly string commandLine;

        internal OneHeldRun(FakeBd bd, string commandLine)
        {
            this.bd = bd;
            this.commandLine = commandLine;
        }

        internal TaskCompletionSource<BdResult> Answer { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        /// <summary>Answers this run as bd itself would have.</summary>
        public void Answers(string standardOutput) => bd.Release(Answer, commandLine, standardOutput);
    }

    private sealed record HeldRun(TaskCompletionSource<BdResult> Answer, TaskCompletionSource Started);
}
