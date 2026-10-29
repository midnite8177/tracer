using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;

namespace JidokaUi.Tests.Boards;

public sealed class BeadQuestionTests
{
    private const string TheOptions =
        """[{\"name\":\"Use the cheap plan\",\"confidence\":80},{\"name\":\"Keep the dear plan\",\"confidence\":20}]""";

    [Fact]
    public void ReadsTheOptionsAndTheRecommendationThatJidokaKeepsInTheMetadataOfABead()
    {
        var bead = TheBead($$"""
            "metadata": {"question.options": "{{TheOptions}}", "question.recommended": "Use the cheap plan"}
            """);

        var question = Assert.IsType<BeadQuestion>(bead.Question);
        Assert.Equal(
            [new QuestionOption("Use the cheap plan", 80), new QuestionOption("Keep the dear plan", 20)],
            question.Options);
        Assert.Equal("Use the cheap plan", question.Recommended);
    }

    [Fact]
    public void ReadsTheOptionsWhenBdPrintsThemAsAnArrayAndNotAsAString()
    {
        var bead = TheBead("""
            "metadata": {"question.options": [{"name": "Yes", "confidence": 90}, {"name": "No", "confidence": 10}],
                         "question.recommended": "Yes"}
            """);

        Assert.Equal(["Yes", "No"], bead.Question?.Options.Select(option => option.Name));
    }

    [Fact]
    public void MarksTheOptionThatTheRecommendationNames()
    {
        var question = Assert.IsType<BeadQuestion>(TheBead($$"""
            "metadata": {"question.options": "{{TheOptions}}", "question.recommended": "Keep the dear plan"}
            """).Question);

        Assert.Equal(
            ["Keep the dear plan"],
            question.Options.Where(question.Recommends).Select(option => option.Name));
    }

    [Fact]
    public void MarksNoOptionWhenTheMetadataKeepsNoRecommendation()
    {
        var question = Assert.IsType<BeadQuestion>(TheBead($$"""
            "metadata": {"question.options": "{{TheOptions}}"}
            """).Question);

        Assert.DoesNotContain(question.Options, question.Recommends);
    }

    [Fact]
    public void GivesNoQuestionToABeadWhoseMetadataKeepsNoOptions()
    {
        Assert.Null(TheBead("""
            "metadata": {"lap.stage": "build"}
            """).Question);
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("{}")]
    [InlineData("[]")]
    [InlineData("""[{\"confidence\":50}]""")]
    public void GivesNoQuestionWhenTheOptionsNameNoAnswer(string options)
    {
        Assert.Null(TheBead($$"""
            "metadata": {"question.options": "{{options}}"}
            """).Question);
    }

    private static Bead TheBead(string field)
    {
        var printed = $$"""[{"id": "b-7", "title": "Pick a hosting plan", "labels": ["human"], {{field}} }]""";
        Assert.True(BdJson.TryParse(printed, out var records));
        return Bead.From(Assert.Single(records));
    }
}
