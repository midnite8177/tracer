using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Beads;

public sealed class BdWriteTests
{
    private static readonly BeadAddress Bead =
        new(ProjectPath.From(Path.GetTempPath()), "x-1");

    private static BeadLabel Label(string word) =>
        BeadLabel.TryFrom(word, out var label)
            ? label
            : throw new InvalidOperationException($"{word} is not a label in this test.");

    [Fact]
    public async Task WritesACommentThroughTheCommentCommandOfBd()
    {
        var bd = BdThatWrites().Prints("comment x-1 I read this today", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.CommentAsync(Bead, "I read this today");

        Assert.True(outcome.Wrote);
        Assert.Equal(string.Empty, outcome.Message);
        Assert.Contains("comment x-1 I read this today", bd.Invocations);
    }

    [Fact]
    public async Task ReportsWhatBdWroteOnStandardErrorWhenTheWriteFails()
    {
        var bd = BdThatWrites().Fails("comment x-1 hello", "issue x-1 not found");
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.CommentAsync(Bead, "hello");

        Assert.False(outcome.Wrote);
        Assert.Contains("issue x-1 not found", outcome.Message);
    }

    [Fact]
    public async Task RefusesAWriteThatTheInstalledBdHasNoCommandFor()
    {
        var bd = new FakeBd()
            .Prints("version", "bd version 1.0.0")
            .Prints("--help", """
                Working With Issues:
                  update            Update one or more issues
                """);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.CommentAsync(Bead, "hello");

        Assert.False(outcome.Wrote);
        Assert.Equal("bd has no comment command.", outcome.Message);
        Assert.DoesNotContain("comment x-1 hello", bd.Invocations);
    }

    [Fact]
    public async Task AddsALabelThroughTheLabelAddCommandOfBd()
    {
        var bd = BdThatWrites().Prints("label add x-1 human", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.AddLabelAsync(Bead, Label("human"));

        Assert.True(outcome.Wrote);
        Assert.Contains("label add x-1 human", bd.Invocations);
    }

    [Fact]
    public async Task RemovesALabelThroughTheLabelRemoveCommandOfBd()
    {
        var bd = BdThatWrites().Prints("label remove x-1 human", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.RemoveLabelAsync(Bead, Label("human"));

        Assert.True(outcome.Wrote);
        Assert.Contains("label remove x-1 human", bd.Invocations);
    }

    [Fact]
    public async Task SetsThePriorityThroughTheUpdateCommandOfBd()
    {
        var bd = BdThatWrites().Prints("update x-1 --priority 1", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.SetPriorityAsync(Bead, 1);

        Assert.True(outcome.Wrote);
        Assert.Contains("update x-1 --priority 1", bd.Invocations);
    }

    [Fact]
    public async Task SetsTheTypeThroughTheUpdateCommandOfBd()
    {
        var bd = BdThatWrites().Prints("update x-1 --type bug", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.SetTypeAsync(Bead, BeadTypeWord.Bug);

        Assert.True(outcome.Wrote);
        Assert.Contains("update x-1 --type bug", bd.Invocations);
    }

    [Fact]
    public async Task SetsTheStatusThroughTheUpdateCommandOfBd()
    {
        var bd = BdThatWrites().Prints("update x-1 --status in_progress", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.SetStatusAsync(Bead, StoredStatusWord.InProgress);

        Assert.True(outcome.Wrote);
        Assert.Contains("update x-1 --status in_progress", bd.Invocations);
    }

    [Fact]
    public async Task ClosesABeadWithTheReasonThatThePersonGave()
    {
        var bd = BdThatWrites().Prints("close x-1 --reason The board shows it now", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.CloseAsync(Bead, "The board shows it now");

        Assert.True(outcome.Wrote);
        Assert.Contains("close x-1 --reason The board shows it now", bd.Invocations);
    }

    [Fact]
    public async Task RefusesACloseThatStatesNoReason()
    {
        var bd = BdThatWrites();
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.CloseAsync(Bead, "   ");

        Assert.False(outcome.Wrote);
        Assert.Equal("A close needs a reason. The history of this bead is what a later reader has.", outcome.Message);
        Assert.DoesNotContain(bd.Invocations, invocation => invocation.StartsWith("close ", StringComparison.Ordinal));
    }

    [Fact]
    public async Task MovesABeadIntoAnEpicThroughTheParentFlagOfBd()
    {
        var bd = BdThatWrites().Prints("update x-1 --parent x-9", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.SetParentAsync(Bead, "x-9");

        Assert.True(outcome.Wrote);
        Assert.Contains("update x-1 --parent x-9", bd.Invocations);
    }

    [Fact]
    public async Task DefersABeadThroughTheDeferCommandOfBd()
    {
        var bd = BdThatWrites().Prints("defer x-1", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.DeferAsync(Bead);

        Assert.True(outcome.Wrote);
        Assert.Contains("defer x-1", bd.Invocations);
    }

    [Fact]
    public async Task RefusesALabelWriteWhenTheLabelCommandOfTheInstalledBdHasNoSuchSubcommand()
    {
        var bd = new FakeBd()
            .Prints("version", "bd version 1.0.0")
            .Prints("--help", """
                Working With Issues:
                  label             Manage issue labels
                """)
            .Prints("label --help", """
                Available Commands:
                  add       Add a label to one or more issues
                """);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.RemoveLabelAsync(Bead, Label("human"));

        Assert.False(outcome.Wrote);
        Assert.Equal("bd label has no remove subcommand.", outcome.Message);
        Assert.DoesNotContain("label remove x-1 human", bd.Invocations);
    }

    [Fact]
    public async Task WritesTheTitleAndTheDescriptionTogetherThroughTheUpdateCommandOfBd()
    {
        var bd = BdThatWrites().Prints("update x-1 --title A sharper title --description ## Demo\nIt runs.", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.EditProseAsync(Bead, "A sharper title", "## Demo\nIt runs.");

        Assert.True(outcome.Wrote);
        Assert.Contains("update x-1 --title A sharper title --description ## Demo\nIt runs.", bd.Invocations);
    }

    [Fact]
    public async Task RefusesAProseEditThatLeavesTheBeadWithNoTitle()
    {
        var bd = BdThatWrites();
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.EditProseAsync(Bead, "   ", "The description stays.");

        Assert.False(outcome.Wrote);
        Assert.Equal("A bead needs a title.", outcome.Message);
        Assert.DoesNotContain(bd.Invocations, invocation => invocation.StartsWith("update ", StringComparison.Ordinal));
    }

    [Fact]
    public async Task RewritesTheNotesThroughTheFlagOfBdThatReplacesThemRatherThanAppendsToThem()
    {
        var bd = BdThatWrites().Prints("update x-1 --notes The whole of the new notes.", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.RewriteNotesAsync(Bead, "The whole of the new notes.");

        Assert.True(outcome.Wrote);
        Assert.Contains("update x-1 --notes The whole of the new notes.", bd.Invocations);
        Assert.DoesNotContain(bd.Invocations, invocation => invocation.Contains("--append-notes", StringComparison.Ordinal));
    }

    [Fact]
    public async Task AddsACommentWithoutAWriteToTheNotesOfTheBead()
    {
        var bd = BdThatWrites().Prints("comment x-1 I read this today", string.Empty);
        var adapter = new BdAdapter(bd);

        await adapter.CommentAsync(Bead, "I read this today");

        Assert.DoesNotContain(bd.Invocations, invocation => invocation.Contains("--notes", StringComparison.Ordinal));
    }

    [Fact]
    public async Task AddsABlockerThroughTheDepAddCommandOfBd()
    {
        var bd = BdThatWrites().Prints("dep add x-1 x-9", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.AddBlockerAsync(Bead, "x-9");

        Assert.True(outcome.Wrote);
        Assert.Contains("dep add x-1 x-9", bd.Invocations);
    }

    [Fact]
    public async Task RemovesABlockerThroughTheDepRemoveCommandOfBd()
    {
        var bd = BdThatWrites().Prints("dep remove x-1 x-9", string.Empty);
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.RemoveBlockerAsync(Bead, "x-9");

        Assert.True(outcome.Wrote);
        Assert.Contains("dep remove x-1 x-9", bd.Invocations);
    }

    [Fact]
    public async Task RefusesADependencyEdgeThatNamesNoBlockerAtItsFarEnd()
    {
        var bd = BdThatWrites();
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.AddBlockerAsync(Bead, "  ");

        Assert.False(outcome.Wrote);
        Assert.Equal("An edge needs the blocker at its far end.", outcome.Message);
        Assert.DoesNotContain(bd.Invocations, invocation => invocation.StartsWith("dep ", StringComparison.Ordinal));
    }

    [Fact]
    public async Task RefusesADependencyEdgeFromABeadToItself()
    {
        var bd = BdThatWrites();
        var adapter = new BdAdapter(bd);

        var outcome = await adapter.AddBlockerAsync(Bead, "x-1");

        Assert.False(outcome.Wrote);
        Assert.Equal("A bead cannot block itself.", outcome.Message);
        Assert.DoesNotContain("dep add x-1 x-1", bd.Invocations);
    }

    // A bd whose help declares every command, subcommand and flag that a single-bead write needs.
    private static FakeBd BdThatWrites() => new FakeBd().DeclaresEveryWrite();
}
