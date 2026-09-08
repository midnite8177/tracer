using TracerUi.Core.Look;

namespace TracerUi.Tests.Look;

public sealed class NewTabFeedbackTests
{
    [Fact]
    public void GivesNoReasonBeforeAnyReleaseAsksForANewTab()
    {
        var feedback = new NewTabFeedback();

        Assert.Equal(NewTabOutcome.None, feedback.Outcome);
        Assert.Null(feedback.Reason);
    }

    [Fact]
    public void GivesAReasonWhenTheBrowserRefusesTheTab()
    {
        var feedback = new NewTabFeedback();

        feedback.Take(NewTabOutcome.Refused);

        Assert.Equal(NewTabOutcome.Refused, feedback.Outcome);
        Assert.NotNull(feedback.Reason);
    }

    [Fact]
    public void NamesWhatToDoInsteadOfTheTabThatTheBrowserRefused()
    {
        var feedback = new NewTabFeedback();

        feedback.Take(NewTabOutcome.Refused);

        Assert.Contains("popups", feedback.Reason);
    }

    [Fact]
    public void DropsTheReasonWhenALaterReleasePutsTheBeadInFrontOfThePerson()
    {
        var feedback = new NewTabFeedback();

        feedback.Take(NewTabOutcome.Refused);
        feedback.Take(NewTabOutcome.None);

        Assert.Equal(NewTabOutcome.None, feedback.Outcome);
        Assert.Null(feedback.Reason);
    }
}
