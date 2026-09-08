using TracerUi.Core.Look;

namespace TracerUi.Tests.Look;

public sealed class CopyFeedbackTests
{
    [Fact]
    public void MarksNoTextBeforeAPersonPressesAnyCopyButton()
    {
        var feedback = new CopyFeedback();

        Assert.Equal(CopyOutcome.None, feedback.Outcome("tracer-1"));
    }

    [Fact]
    public void MarksTheTextThatAPersonCopiedAndNoOtherText()
    {
        var feedback = new CopyFeedback();

        feedback.Took("tracer-1");

        Assert.Equal(CopyOutcome.Took, feedback.Outcome("tracer-1"));
        Assert.Equal(CopyOutcome.None, feedback.Outcome("tracer-2"));
    }

    [Fact]
    public void MarksNoEmptyTextBecauseTheClipboardTakesNothingFromIt()
    {
        var feedback = new CopyFeedback();

        feedback.Took("");

        Assert.Equal(CopyOutcome.None, feedback.Outcome(""));
    }

    [Fact]
    public void AsksForACopyOfTheTextThatNoPersonPressedAButtonFor()
    {
        var feedback = new CopyFeedback();

        Assert.Equal("Copy tracer-1", feedback.Says("tracer-1"));
    }

    [Fact]
    public void SaysThatTheCopyLandedForTheTextThatThePersonCopied()
    {
        var feedback = new CopyFeedback();

        feedback.Took("tracer-1");

        Assert.Equal("Copied tracer-1", feedback.Says("tracer-1"));
        Assert.Equal("Copy tracer-2", feedback.Says("tracer-2"));
    }

    [Fact]
    public void TellsEveryCopyButtonToDrawItselfAgainWhenTheMarkMoves()
    {
        var feedback = new CopyFeedback();
        var told = 0;
        feedback.Changed += () => told++;

        feedback.Took("tracer-1");
        feedback.Took("tracer-2");

        Assert.Equal(2, told);
    }

    [Fact]
    public void AsksForASecureConnectionWhenThePageReachesNoClipboard()
    {
        var feedback = new CopyFeedback();

        feedback.FoundNoClipboard("tracer-1");

        Assert.Equal(CopyOutcome.NoClipboard, feedback.Outcome("tracer-1"));
        Assert.Equal(
            "Cannot copy tracer-1. The browser needs a secure connection.",
            feedback.Says("tracer-1"));
    }

    [Fact]
    public void BlamesNoSecureConnectionWhenTheBrowserHadAClipboardAndStillSaidNo()
    {
        var feedback = new CopyFeedback();

        feedback.Refused("tracer-1");

        Assert.Equal(CopyOutcome.Refused, feedback.Outcome("tracer-1"));
        Assert.Equal(
            "Cannot copy tracer-1. The browser would not write to the clipboard.",
            feedback.Says("tracer-1"));
    }

    [Fact]
    public void TakesTheMarkOffATextThatTheBrowserLaterRefused()
    {
        var feedback = new CopyFeedback();

        feedback.Took("tracer-1");
        feedback.Refused("tracer-1");

        Assert.Equal(CopyOutcome.Refused, feedback.Outcome("tracer-1"));
    }

    [Fact]
    public void ForgetsARefusalWhenALaterPressPutsTheSameTextOnTheClipboard()
    {
        var feedback = new CopyFeedback();

        feedback.Refused("tracer-1");
        feedback.Took("tracer-1");

        Assert.Equal(CopyOutcome.Took, feedback.Outcome("tracer-1"));
        Assert.Equal("Copied tracer-1", feedback.Says("tracer-1"));
    }

    [Fact]
    public void MarksNoEmptyTextThatFoundNoClipboardBecauseNoButtonAsksForOne()
    {
        var feedback = new CopyFeedback();

        feedback.FoundNoClipboard("");

        Assert.Equal(CopyOutcome.None, feedback.Outcome(""));
        Assert.Equal("Copy ", feedback.Says(""));
    }

    [Fact]
    public void MarksOneTextAtATimeWhateverTheBrowserDidWithTheTextBefore()
    {
        var feedback = new CopyFeedback();

        feedback.FoundNoClipboard("tracer-1");
        feedback.Took("tracer-2");

        Assert.Equal(CopyOutcome.None, feedback.Outcome("tracer-1"));
        Assert.Equal(CopyOutcome.Took, feedback.Outcome("tracer-2"));
    }
}
