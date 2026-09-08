using TracerUi.Core.Beads;

namespace TracerUi.Tests.Beads;

/// <summary>A bd that gives scripted stdout and stderr, so that a test fixes one version shape.</summary>
public sealed class FakeBd : IBdProcess
{
    private readonly Dictionary<string, BdResult> scripted = new(StringComparer.Ordinal);

    private readonly Dictionary<(string Directory, string CommandLine), BdResult> scriptedPerDirectory = [];
    private readonly List<(string Directory, string CommandLine)> runs = [];
    private readonly Dictionary<string, Action<FakeBd>> changes = new(StringComparer.Ordinal);

    /// <summary>The command lines that the code under test ran, in order.</summary>
    public List<string> Invocations { get; } = [];

    /// <summary>How many times the code under test ran this command line in this directory.</summary>
    public int Runs(string workingDirectory, string commandLine) =>
        runs.Count(run =>
            string.Equals(run.Directory, workingDirectory, StringComparison.Ordinal)
            && string.Equals(run.CommandLine, commandLine, StringComparison.Ordinal));

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
        scripted[commandLine] = new BdResult(0, standardOutput, string.Empty);
        return this;
    }

    /// <summary>
    /// Scripts the answer that this bd gives one command line in one directory alone, so that a test
    /// fixes a different shape per project.
    /// </summary>
    public FakeBd PrintsIn(string workingDirectory, string commandLine, string standardOutput)
    {
        scriptedPerDirectory[(workingDirectory, commandLine)] = new BdResult(0, standardOutput, string.Empty);
        return this;
    }

    public FakeBd Fails(string commandLine, string standardError)
    {
        scripted[commandLine] = new BdResult(1, string.Empty, standardError);
        return this;
    }

    public Task<BdResult> RunAsync(string workingDirectory, IReadOnlyList<string> arguments)
    {
        var commandLine = string.Join(' ', arguments);
        Invocations.Add(commandLine);
        runs.Add((workingDirectory, commandLine));
        var answer = Answer(workingDirectory, commandLine, arguments[0]);
        if (changes.TryGetValue(commandLine, out var change))
        {
            change(this);
        }

        return Task.FromResult(answer);
    }

    // The scripted answer for this directory, or the one that every directory shares, or the
    // failure that a bd gives a command it does not have.
    private BdResult Answer(string workingDirectory, string commandLine, string verb)
    {
        if (scriptedPerDirectory.TryGetValue((workingDirectory, commandLine), out var here))
        {
            return here;
        }

        return scripted.TryGetValue(commandLine, out var anywhere)
            ? anywhere
            : new BdResult(1, string.Empty, $"unknown command \"{verb}\" for \"bd\"");
    }
}
