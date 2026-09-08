using Bunit;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Boards;
using TracerUi.Core.Look;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Boards;

/// <summary>The appearance of a resolved status, and the class that a bead row draws for it.</summary>
public sealed class BeadStatusAppearanceTests : BunitContext
{
    private static BeadStatus Of(BeadStatusKind kind) => new(kind, "any detail", []);

    private static IReadOnlyList<BeadStatusKind> EveryKind => Enum.GetValues<BeadStatusKind>();

    [Fact]
    public void GivesEachResolvedStatusAnAppearanceOfItsOwn()
    {
        var appearances = EveryKind.Select(kind => Of(kind).Appearance).ToList();

        Assert.Equal(appearances.Count, appearances.Distinct(StringComparer.Ordinal).Count());
    }

    [Fact]
    public void GivesAnAppearanceToEveryResolvedStatus()
    {
        Assert.All(EveryKind, kind => Assert.NotEmpty(Of(kind).Appearance));
    }

    [Theory]
    [InlineData(BeadStatusKind.NeedsYou, "needs-you")]
    [InlineData(BeadStatusKind.Deferred, "deferred")]
    [InlineData(BeadStatusKind.InProgress, "in-progress")]
    [InlineData(BeadStatusKind.Ready, "ready")]
    [InlineData(BeadStatusKind.Blocked, "blocked")]
    [InlineData(BeadStatusKind.AsBdSaysIt, "stored")]
    [InlineData(BeadStatusKind.NotInThisBacklog, "unknown")]
    public void DrawsTheDotOfABeadRowInTheClassThatTheStylesheetColors(
        BeadStatusKind kind,
        string appearance)
    {
        var row = TheRowOfABeadThatIs(kind);

        Assert.Contains($"bead-status-{appearance}", row.Find(".bead-dot").ClassList);
    }

    private IRenderedComponent<BeadRow> TheRowOfABeadThatIs(BeadStatusKind kind)
    {
        Services.AddSingleton(new CopyFeedback());
        return Render<BeadRow>(row => row.Add(
            it => it.Link,
            new BeadLink("x-1", "First", "task", Of(kind))));
    }
}
