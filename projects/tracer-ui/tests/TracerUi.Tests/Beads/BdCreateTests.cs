using TracerUi.Core.Beads;
using TracerUi.Core.Projects;
using TracerUi.Tests;

namespace TracerUi.Tests.Beads;

public sealed class BdCreateTests
{
    private static readonly ProjectPath Project = ProjectPath.From(Path.GetTempPath());

    [Fact]
    public async Task CreatesABeadFromATitleAndATypeAndGivesBackTheIdThatBdPrinted()
    {
        var bd = BdThatCreates().Prints("create --title Read the docs --type task --silent", "x-7\n");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.CreateAsync(Project, "Read the docs", "task", null);

        Assert.True(outcome.Created);
        Assert.Equal("x-7", outcome.Id);
        Assert.Equal(string.Empty, outcome.Message);
    }

    [Fact]
    public async Task CreatesABeadInsideTheEpicThatThePersonPicked()
    {
        var bd = BdThatCreates()
            .Prints("create --title Read the docs --type task --parent x-9 --silent", "x-9.1\n");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.CreateAsync(Project, "Read the docs", "task", "x-9");

        Assert.True(outcome.Created);
        Assert.Equal("x-9.1", outcome.Id);
    }

    [Fact]
    public async Task RefusesACreateThatStatesNoTitle()
    {
        var bd = BdThatCreates();
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.CreateAsync(Project, "   ", "task", null);

        Assert.False(outcome.Created);
        Assert.Equal("A bead needs a title.", outcome.Message);
        Assert.DoesNotContain(bd.Invocations, invocation => invocation.StartsWith("create --title", StringComparison.Ordinal));
    }

    [Fact]
    public async Task SetsANewEpicToInProgressAtOnceSoThatItNeverReadsAsWork()
    {
        var bd = BdThatCreates()
            .Prints("create --title The migration --type epic --silent", "x-4\n")
            .Prints("update x-4 --status in_progress", string.Empty);
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.CreateEpicAsync(Project, "The migration");

        Assert.True(outcome.Created);
        Assert.Equal("x-4", outcome.Id);
        Assert.Equal(string.Empty, outcome.Message);
        Assert.Contains("update x-4 --status in_progress", bd.Invocations);
    }

    [Fact]
    public async Task SaysThatTheEpicExistsWhenBdWouldNotSetItToInProgress()
    {
        var bd = BdThatCreates()
            .Prints("create --title The migration --type epic --silent", "x-4\n")
            .Fails("update x-4 --status in_progress", "unknown status \"in_progress\"");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.CreateEpicAsync(Project, "The migration");

        Assert.True(outcome.Created);
        Assert.Equal("x-4", outcome.Id);
        Assert.Contains("bd made the epic x-4, but it is still open.", outcome.Message);
        Assert.Contains("unknown status \"in_progress\"", outcome.Message);
    }

    [Fact]
    public async Task ReportsWhatBdWroteOnStandardErrorWhenTheCreateFails()
    {
        var bd = BdThatCreates().Fails("create --title Read the docs --type task --silent", "prefix mismatch");
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.CreateAsync(Project, "Read the docs", "task", null);

        Assert.False(outcome.Created);
        Assert.Contains("prefix mismatch", outcome.Message);
        Assert.Equal(string.Empty, outcome.Id);
    }

    [Fact]
    public async Task RefusesACreateInsideAnEpicWhenTheCreateOfTheInstalledBdHasNoParentFlag()
    {
        var bd = BdWithoutTheParentFlag();
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.CreateAsync(Project, "Read the docs", "task", "x-9");

        Assert.False(outcome.Created);
        Assert.Equal("bd create has no --parent flag.", outcome.Message);
        Assert.DoesNotContain(bd.Invocations, invocation => invocation.StartsWith("create --title", StringComparison.Ordinal));
    }

    [Fact]
    public async Task GivesUpOnACreateThatOutrunsTheWaitLimitAndSaysItMayStillHaveLanded()
    {
        var bd = BdThatCreates().Holds("create --title Read the docs --type task --silent");
        var clock = new FakeTimeProvider(new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
        var adapter = new BdAdapter(bd, clock);

        var creating = adapter.CreateAsync(Project, "Read the docs", "task", null);
        clock.Advance(BdAdapter.WaitLimit);
        var outcome = await creating;

        Assert.False(outcome.Created);
        Assert.True(outcome.GaveUp);
        Assert.Contains("may still have landed", outcome.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task RefusesAMoveIntoAnEpicWhenTheUpdateOfTheInstalledBdHasNoParentFlag()
    {
        var bd = BdWithoutTheParentFlag();
        var adapter = new BdAdapter(bd, TimeProvider.System);

        var outcome = await adapter.SetParentAsync(new BeadAddress(Project, "x-1"), "x-9");

        Assert.False(outcome.Wrote);
        Assert.Equal("bd update has no --parent flag.", outcome.Message);
        Assert.DoesNotContain("update x-1 --parent x-9", bd.Invocations);
    }

    // A bd of a version that cannot re-parent, on the create or on the update.
    private static FakeBd BdWithoutTheParentFlag() =>
        new FakeBd()
            .Prints("version", "bd version 1.0.0")
            .Prints("--help", """
                Working With Issues:
                  create            Create a new issue
                  update            Update one or more issues
                """)
            .Prints("create --help", """
                Flags:
                      --silent        Output only the issue ID (for scripting)
                      --title string  Issue title
                  -t, --type string   Issue type
                """)
            .Prints("update --help", """
                Flags:
                  -s, --status string   New status
                """);

    // A bd whose help declares the commands, subcommands and flags that a create needs.
    private static FakeBd BdThatCreates() =>
        new FakeBd()
            .Prints("version", "bd version 1.2.2")
            .Prints("--help", """
                Working With Issues:
                  create            Create a new issue
                  update            Update one or more issues
                """)
            .Prints("create --help", """
                Flags:
                      --parent string   Parent issue ID for hierarchical child
                      --silent          Output only the issue ID (for scripting)
                      --title string    Issue title
                  -t, --type string     Issue type
                """)
            .Prints("update --help", """
                Flags:
                      --parent string   The epic that holds this issue
                  -s, --status string   New status
                """);
}
