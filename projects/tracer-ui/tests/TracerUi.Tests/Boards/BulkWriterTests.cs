using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using TracerUi.Tests.Beads;

namespace TracerUi.Tests.Boards;

public sealed class BulkWriterTests
{
    private static readonly ProjectPath Project = ProjectPath.From(Path.GetTempPath());

    [Fact]
    public async Task WritesTheLabelOnceForEveryBeadOfThePlan()
    {
        var bd = BdThatWrites()
            .Prints("label add x-1 human", string.Empty)
            .Prints("label add x-2 human", string.Empty);
        var writer = new BulkWriter(new BdAdapter(bd));

        var report = await writer.RunAsync(Project, BulkPlan.For(BulkAction.AddTheLabel("human"), TwoBeads));

        Assert.True(report.Whole);
        Assert.Equal(2, report.Written);
        Assert.Contains("label add x-1 human", bd.Invocations);
        Assert.Contains("label add x-2 human", bd.Invocations);
    }

    [Fact]
    public async Task NamesTheProjectOnceForTheWholeSelectionAndNotOncePerBead()
    {
        var bd = BdThatWrites()
            .Prints("label add x-1 human", string.Empty)
            .Prints("label add x-2 human", string.Empty);
        var adapter = new BdAdapter(bd);
        var named = new List<ProjectPath>();
        adapter.Wrote += project => named.Add(project);

        await new BulkWriter(adapter)
            .RunAsync(Project, BulkPlan.For(BulkAction.AddTheLabel("human"), TwoBeads));

        Assert.Equal([Project], named);
    }

    [Fact]
    public async Task NamesTheBeadThatFailedAndStillWritesTheRestOfTheSelection()
    {
        var bd = BdThatWrites()
            .Prints("label add x-1 human", string.Empty)
            .Fails("label add x-2 human", "issue x-2 not found");
        var writer = new BulkWriter(new BdAdapter(bd));

        var report = await writer.RunAsync(Project, BulkPlan.For(BulkAction.AddTheLabel("human"), TwoBeads));

        Assert.False(report.Whole);
        Assert.Equal(1, report.Written);
        Assert.Equal(["x-2"], report.Failures.Select(failure => failure.BeadId));
        Assert.Contains("issue x-2 not found", report.Failures[0].Message);
    }

    [Fact]
    public async Task ClosesEachBeadWithTheReasonThatThePlanHoldsForThatBead()
    {
        var bd = BdThatWrites()
            .Prints("close x-1 --reason Stale", string.Empty)
            .Prints("close x-2 --reason This one shipped", string.Empty);
        var writer = new BulkWriter(new BdAdapter(bd));
        var plan = BulkPlan.For(BulkAction.CloseThem("Stale"), TwoBeads)
            .WithReasonFor("x-2", "This one shipped");

        var report = await writer.RunAsync(Project, plan);

        Assert.True(report.Whole);
        Assert.Contains("close x-1 --reason Stale", bd.Invocations);
        Assert.Contains("close x-2 --reason This one shipped", bd.Invocations);
    }

    [Fact]
    public async Task RunsNothingWhenThePlanIsNotReadyToCommit()
    {
        var bd = BdThatWrites();
        var writer = new BulkWriter(new BdAdapter(bd));
        var plan = BulkPlan.For(BulkAction.CloseThem("Stale"), TwoBeads).WithReasonFor("x-1", "  ");

        var report = await writer.RunAsync(Project, plan);

        Assert.Equal(0, report.Written);
        Assert.Equal("Bead x-1 has no close reason.", report.Message);
        Assert.DoesNotContain(bd.Invocations, invocation => invocation.StartsWith("close ", StringComparison.Ordinal));
    }

    [Fact]
    public async Task RunsTheCommandThatEachVerbCategoryOfTheActionBarNeeds()
    {
        var bd = BdThatWrites();
        var writer = new BulkWriter(new BdAdapter(bd));
        IReadOnlyList<Bead> one = [ABead.Called("x-1", "One")];

        foreach (var action in EveryVerbCategory)
        {
            await writer.RunAsync(Project, BulkPlan.For(action, one));
        }

        Assert.Equal(
            [
                "label add x-1 human",
                "label remove x-1 human",
                "close x-1 --reason Stale",
                "defer x-1",
                "update x-1 --parent x-9",
                "update x-1 --priority 1",
                "update x-1 --type bug",
            ],
            bd.Invocations.Where(invocation => invocation.Contains("x-1", StringComparison.Ordinal)));
    }

    [Fact]
    public async Task ReportsHowManyBeadsBdWroteAndHowManyOfThemFailed()
    {
        var whole = BdThatWrites()
            .Prints("defer x-1", string.Empty)
            .Prints("defer x-2", string.Empty);
        var partial = BdThatWrites()
            .Prints("defer x-1", string.Empty)
            .Fails("defer x-2", "issue x-2 not found");

        var everyBead = await new BulkWriter(new BdAdapter(whole))
            .RunAsync(Project, BulkPlan.For(BulkAction.DeferThem(), TwoBeads));
        var oneShort = await new BulkWriter(new BdAdapter(partial))
            .RunAsync(Project, BulkPlan.For(BulkAction.DeferThem(), TwoBeads));

        Assert.Equal("bd wrote 2 beads.", everyBead.Summary);
        Assert.Equal("bd wrote 1 bead. 1 failed.", oneShort.Summary);
    }

    private static IReadOnlyList<BulkAction> EveryVerbCategory =>
        [
            BulkAction.AddTheLabel("human"),
            BulkAction.RemoveTheLabel("human"),
            BulkAction.CloseThem("Stale"),
            BulkAction.DeferThem(),
            BulkAction.MoveIntoTheEpic("x-9"),
            BulkAction.SetThePriority(1),
            BulkAction.SetTheType("bug"),
        ];

    private static IReadOnlyList<Bead> TwoBeads =>
        [ABead.Called("x-1", "One"), ABead.Called("x-2", "Two")];

    // A bd whose help declares every command and flag that the action bar needs.
    private static FakeBd BdThatWrites() =>
        new FakeBd()
            .Prints("version", "bd version 1.2.2")
            .Prints("--help", """
                Working With Issues:
                  close             Close one or more issues
                  comment           Add a comment to an issue
                  defer             Defer one or more issues for later
                  label             Manage issue labels
                  update            Update one or more issues
                """)
            .Prints("close --help", """
                Flags:
                  -r, --reason string   Reason for closing
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
                      --parent string          The epic that holds this issue
                  -p, --priority string        Priority
                  -s, --status string          New status
                  -t, --type string            New type
                """);
}
