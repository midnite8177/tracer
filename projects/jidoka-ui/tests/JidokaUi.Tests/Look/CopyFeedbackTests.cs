using JidokaUi.Core.Look;

namespace JidokaUi.Tests.Look;

public sealed class CopyFeedbackTests
{
    [Fact]
    public void MarksNoTextBeforeAPersonPressesAnyCopyButton()
    {
        var feedback = new CopyFeedback();

        Assert.Equal(CopyOutcome.None, feedback.Outcome("jidoka-1"));
    }

    [Fact]
    public void MarksTheTextThatAPersonCopiedAndNoOtherText()
    {
        var feedback = new CopyFeedback();

        feedback.Took("jidoka-1");

        Assert.Equal(CopyOutcome.Took, feedback.Outcome("jidoka-1"));
        Assert.Equal(CopyOutcome.None, feedback.Outcome("jidoka-2"));
    }

    [Fact]
    public void MarksTheEmptyTextTheSameWayItMarksAnyOtherText()
    {
        var feedback = new CopyFeedback();

        feedback.Took("");

        Assert.Equal(CopyOutcome.Took, feedback.Outcome(""));
    }

    [Fact]
    public void AsksForACopyOfTheTextThatNoPersonPressedAButtonFor()
    {
        var feedback = new CopyFeedback();

        Assert.Equal("Copy jidoka-1", feedback.Says("jidoka-1"));
    }

    [Fact]
    public void SaysThatTheCopyLandedForTheTextThatThePersonCopied()
    {
        var feedback = new CopyFeedback();

        feedback.Took("jidoka-1");

        Assert.Equal("Copied jidoka-1", feedback.Says("jidoka-1"));
        Assert.Equal("Copy jidoka-2", feedback.Says("jidoka-2"));
    }

    [Fact]
    public void TellsEveryCopyButtonToDrawItselfAgainWhenTheMarkMoves()
    {
        var feedback = new CopyFeedback();
        var told = 0;
        feedback.Changed += () => told++;

        feedback.Took("jidoka-1");
        feedback.Took("jidoka-2");

        Assert.Equal(2, told);
    }

    [Fact]
    public void AsksForASecureConnectionWhenThePageReachesNoClipboard()
    {
        var feedback = new CopyFeedback();

        feedback.FoundNoClipboard("jidoka-1");

        Assert.Equal(CopyOutcome.NoClipboard, feedback.Outcome("jidoka-1"));
        Assert.Equal(
            "Cannot copy jidoka-1. The browser needs a secure connection.",
            feedback.Says("jidoka-1"));
    }

    [Fact]
    public void BlamesNoSecureConnectionWhenTheBrowserHadAClipboardAndStillSaidNo()
    {
        var feedback = new CopyFeedback();

        feedback.Refused("jidoka-1");

        Assert.Equal(CopyOutcome.Refused, feedback.Outcome("jidoka-1"));
        Assert.Equal(
            "Cannot copy jidoka-1. The browser would not write to the clipboard.",
            feedback.Says("jidoka-1"));
    }

    [Fact]
    public void TakesTheMarkOffATextThatTheBrowserLaterRefused()
    {
        var feedback = new CopyFeedback();

        feedback.Took("jidoka-1");
        feedback.Refused("jidoka-1");

        Assert.Equal(CopyOutcome.Refused, feedback.Outcome("jidoka-1"));
    }

    [Fact]
    public void ForgetsARefusalWhenALaterPressPutsTheSameTextOnTheClipboard()
    {
        var feedback = new CopyFeedback();

        feedback.Refused("jidoka-1");
        feedback.Took("jidoka-1");

        Assert.Equal(CopyOutcome.Took, feedback.Outcome("jidoka-1"));
        Assert.Equal("Copied jidoka-1", feedback.Says("jidoka-1"));
    }

    [Fact]
    public void AsksForASecureConnectionForTheEmptyTextTheSameWayItDoesForAnyOtherText()
    {
        var feedback = new CopyFeedback();

        feedback.FoundNoClipboard("");

        Assert.Equal(CopyOutcome.NoClipboard, feedback.Outcome(""));
        Assert.Equal("Cannot copy . The browser needs a secure connection.", feedback.Says(""));
    }

    [Fact]
    public void MarksOneTextAtATimeWhateverTheBrowserDidWithTheTextBefore()
    {
        var feedback = new CopyFeedback();

        feedback.FoundNoClipboard("jidoka-1");
        feedback.Took("jidoka-2");

        Assert.Equal(CopyOutcome.None, feedback.Outcome("jidoka-1"));
        Assert.Equal(CopyOutcome.Took, feedback.Outcome("jidoka-2"));
    }
}
