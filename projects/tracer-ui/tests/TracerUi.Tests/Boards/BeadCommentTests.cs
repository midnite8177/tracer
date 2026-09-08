using TracerUi.Core.Beads;
using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BeadCommentTests
{
    private static BeadComment Read(string json)
    {
        Assert.True(BdJson.TryParse(json, out var records));
        return BeadComment.From(records.Single());
    }

    [Fact]
    public void ReadsTheAuthorTheTextAndTheMomentOfAComment()
    {
        var comment = Read("""
            {"author": "claude", "text": "Looks good", "created_at": "2026-01-02T09:30:00Z"}
            """);

        Assert.Equal("claude", comment.Author);
        Assert.Equal("Looks good", comment.Text);
        Assert.Equal(new DateTimeOffset(2026, 1, 2, 9, 30, 0, TimeSpan.Zero), comment.At);
    }

    [Fact]
    public void ReadsTheNamesThatAnOlderBdGivesTheSameThreeFields()
    {
        var comment = Read("""
            {"created_by": "sam", "body": "Retry it", "timestamp": "2026-01-02T09:30:00Z"}
            """);

        Assert.Equal("sam", comment.Author);
        Assert.Equal("Retry it", comment.Text);
        Assert.NotNull(comment.At);
    }

    [Fact]
    public void ShowsWhatBdPrintedWhenTheMomentIsNotATimeAtAll()
    {
        var comment = Read("""{"text": "Looks good", "created_at": "the other day"}""");

        Assert.Null(comment.At);
        Assert.Equal("the other day", comment.Timestamp);
    }

    [Fact]
    public void ShowsNoTimestampForACommentThatCarriesNoMoment()
    {
        var comment = Read("""{"text": "Looks good"}""");

        Assert.Null(comment.At);
        Assert.Equal(string.Empty, comment.Timestamp);
    }
}
