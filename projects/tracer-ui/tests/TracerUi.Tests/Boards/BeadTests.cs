using TracerUi.Core.Beads;
using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BeadTests
{
    private static Bead Read(string json)
    {
        Assert.True(BdJson.TryParse(json, out var records));
        return Bead.From(records.Single());
    }

    [Fact]
    public void ReadsTheFieldsThatARowOfTheBoardShows()
    {
        var bead = Read("""
            {
              "id": "x-1",
              "title": "The read-only board",
              "status": "in_progress",
              "priority": 1,
              "issue_type": "task",
              "assignee": "claude",
              "labels": ["human", "meta"],
              "parent": "x",
              "description": "## Demo\n\nBrowse the board.\n"
            }
            """);

        Assert.Equal("x-1", bead.Id);
        Assert.Equal("The read-only board", bead.Title);
        Assert.Equal("in_progress", bead.Status);
        Assert.Equal(1, bead.Priority);
        Assert.Equal("task", bead.Type);
        Assert.Equal("claude", bead.Assignee);
        Assert.Equal(["human", "meta"], bead.Labels);
        Assert.Equal("x", bead.ParentId);
        Assert.Equal("Browse the board.", bead.Prose.DemoLine);
    }

    [Fact]
    public void ReadsTheEpicFromTheParentChildEdgeWhenBdEmitsNoParentField()
    {
        var bead = Read("""
            {
              "id": "x-1",
              "dependencies": [
                {"issue_id": "x-1", "depends_on_id": "x-9", "type": "blocks"},
                {"issue_id": "x-1", "depends_on_id": "x", "type": "parent-child"}
              ]
            }
            """);

        Assert.Equal("x", bead.ParentId);
    }

    [Fact]
    public void HoldsNoEpicAndNoLabelsForABeadThatStatesNeither()
    {
        var bead = Read("""{"id": "x-1", "title": "Alone"}""");

        Assert.Equal(string.Empty, bead.ParentId);
        Assert.Empty(bead.Labels);
        Assert.Equal(Bead.NoPriority, bead.Priority);
    }

    [Fact]
    public void ReadsTheAcceptanceCriteriaAndTheNotesThatTheDetailPageShows()
    {
        var bead = Read("""
            {
              "id": "x-1",
              "acceptance_criteria": "The board shows every bead.",
              "notes": "The probe reads this once."
            }
            """);

        Assert.Equal("The board shows every bead.", bead.Prose.Acceptance);
        Assert.Equal("The probe reads this once.", bead.Prose.Notes);
    }

    [Fact]
    public void ReadsTheBeadsThatBlockThisOneFromItsOwnEdges()
    {
        var bead = Read("""
            {
              "id": "x-1",
              "dependencies": [
                {"id": "x-9", "title": "Groundwork", "dependency_type": "blocks"},
                {"id": "x", "title": "The epic", "dependency_type": "parent-child"}
              ]
            }
            """);

        Assert.Equal(["x-9"], bead.Blockers);
        Assert.Equal("x", bead.ParentId);
    }

    [Fact]
    public void ReadsTheBeadsThatBlockThisOneWhenAnOlderBdNamesTheEdgeDifferently()
    {
        var bead = Read("""
            {
              "id": "x-1",
              "dependencies": [
                {"issue_id": "x-1", "depends_on_id": "x-9", "type": "blocks"}
              ]
            }
            """);

        Assert.Equal(["x-9"], bead.Blockers);
    }
}
