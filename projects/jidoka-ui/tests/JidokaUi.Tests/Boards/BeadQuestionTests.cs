using JidokaUi.Core.Beads;
using JidokaUi.Core.Boards;
using JidokaUi.Core.Jidoka;

namespace JidokaUi.Tests.Boards;

public sealed class BeadQuestionTests
{
    private const string TheOptions =
        """[{\"name\":\"Use the cheap plan\",\"confidence\":80},{\"name\":\"Keep the dear plan\",\"confidence\":20}]""";

    [Fact]
    public void ReadsTheOptionsAndTheRecommendationThatJidokaKeepsInTheMetadataOfABead()
    {
        var question = Assert.IsType<BeadQuestion>(QuestionOn($$"""
            "metadata": {"question.options": "{{TheOptions}}", "question.recommended": "Use the cheap plan"}
            """));

        Assert.Equal(
            [new QuestionOption("Use the cheap plan", 80, null), new QuestionOption("Keep the dear plan", 20, null)],
            question.Options);
        Assert.Equal("Use the cheap plan", question.Recommended);
    }

    [Fact]
    public void ReadsAnOptionWithNoConfidenceAsHavingNone()
    {
        var question = QuestionOn("""
            "metadata": {"question.options": [{"name": "Approve"}, {"name": "Ask back", "confidence": 0}]}
            """);

        Assert.Equal(
            [new QuestionOption("Approve", null, null), new QuestionOption("Ask back", 0, null)],
            question?.Options);
    }

    [Fact]
    public void ReadsWhatHappensNextIfTheHumanPicksEachOption()
    {
        var question = QuestionOn("""
            "metadata": {"question.options": [{"name": "Approve", "next": "The factory builds the epic."},
                                              {"name": "Ask back", "next": "The specs go back to planning."}]}
            """);

        Assert.Equal(
            ["The factory builds the epic.", "The specs go back to planning."],
            question?.Options.Select(option => option.Next));
    }

    [Fact]
    public void ReadsTheOptionsWhenBdPrintsThemAsAnArrayAndNotAsAString()
    {
        var question = QuestionOn("""
            "metadata": {"question.options": [{"name": "Yes", "confidence": 90}, {"name": "No", "confidence": 10}],
                         "question.recommended": "Yes"}
            """);

        Assert.Equal(["Yes", "No"], question?.Options.Select(option => option.Name));
    }

    [Fact]
    public void MarksTheOptionThatTheRecommendationNames()
    {
        var question = Assert.IsType<BeadQuestion>(QuestionOn($$"""
            "metadata": {"question.options": "{{TheOptions}}", "question.recommended": "Keep the dear plan"}
            """));

        Assert.Equal(
            ["Keep the dear plan"],
            question.Options.Where(question.Recommends).Select(option => option.Name));
    }

    [Fact]
    public void MarksNoOptionWhenTheMetadataKeepsNoRecommendation()
    {
        var question = Assert.IsType<BeadQuestion>(QuestionOn($$"""
            "metadata": {"question.options": "{{TheOptions}}"}
            """));

        Assert.DoesNotContain(question.Options, question.Recommends);
    }

    [Fact]
    public void ReadsTheSentenceThatAsksTheQuestion()
    {
        var question = QuestionOn($$"""
            "metadata": {"question.sentence": "Which hosting plan do we buy?", "question.options": "{{TheOptions}}"}
            """);

        Assert.Equal("Which hosting plan do we buy?", question?.Sentence);
    }

    [Fact]
    public void GivesNoSentenceToAQuestionWhoseMetadataKeepsNone()
    {
        var question = Assert.IsType<BeadQuestion>(QuestionOn($$"""
            "metadata": {"question.options": "{{TheOptions}}"}
            """));

        Assert.Null(question.Sentence);
    }

    [Fact]
    public void ReadsTheDeniedCallOfAPermissionQuestionWithTheReasonTheWorkerGaveForIt()
    {
        var question = QuestionOn($$"""
            "metadata": {"question.options": "{{TheOptions}}", "question.call": "cd packages/till && make lint --fix",
                         "question.pattern": "make lint", "question.reason": "The tidy stage needs the linter."}
            """);

        Assert.Equal(
            new DeniedCall("cd packages/till && make lint --fix", "The tidy stage needs the linter."),
            question?.Denied);
    }

    [Fact]
    public void ReadsADeniedCallWithNoReasonWhenTheWorkerGaveNone()
    {
        var question = QuestionOn($$"""
            "metadata": {"question.options": "{{TheOptions}}", "question.call": "make lint", "question.pattern": "make lint"}
            """);

        Assert.Equal(new DeniedCall("make lint", null), question?.Denied);
    }

    [Theory]
    [InlineData("\"question.call\": \"\", \"question.pattern\": \"\",")]
    [InlineData("")]
    public void GivesNoDeniedCallToAQuestionThatIsNoPermissionQuestion(string call)
    {
        var question = Assert.IsType<BeadQuestion>(QuestionOn($$"""
            "metadata": { {{call}} "question.options": "{{TheOptions}}"}
            """));

        Assert.Null(question.Denied);
    }

    [Fact]
    public void GivesNoQuestionToABeadWhoseMetadataKeepsNoOptions()
    {
        Assert.Null(QuestionOn("""
            "metadata": {"lap.stage": "build"}
            """));
    }

    [Theory]
    [InlineData("not json")]
    [InlineData("{}")]
    [InlineData("[]")]
    [InlineData("""[{\"confidence\":50}]""")]
    public void GivesNoQuestionWhenTheOptionsNameNoAnswer(string options)
    {
        Assert.Null(QuestionOn($$"""
            "metadata": {"question.options": "{{options}}"}
            """));
    }

    private static BeadQuestion? QuestionOn(string field)
    {
        var printed = $$"""[{"id": "b-7", "title": "Pick a hosting plan", "labels": ["human"], {{field}} }]""";
        Assert.True(BdJson.TryParse(printed, out var records));
        return JidokaMetadata.QuestionOn(Bead.From(Assert.Single(records)));
    }
}
