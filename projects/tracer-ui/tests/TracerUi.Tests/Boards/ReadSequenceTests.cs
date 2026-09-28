using TracerUi.Web.Components.Pages;

namespace TracerUi.Tests.Boards;

public sealed class ReadSequenceTests
{
    [Fact]
    public void ShowsNoReReadMarkForAFirstReadOfThePerson()
    {
        var reads = new ReadSequence();

        reads.Begin(ReadCause.ThePerson, false);

        Assert.False(reads.Rereading);
    }

    [Fact]
    public void ShowsNoReReadMarkForAReadOfTheProjectWatcher()
    {
        var reads = new ReadSequence();

        reads.Begin(ReadCause.TheProjectWatcher, true);

        Assert.False(reads.Rereading);
    }

    [Fact]
    public void KeepsTheReReadMarkWhenAReadOfTheProjectWatcherThatBeganLaterEndsFirst()
    {
        var reads = new ReadSequence();
        var thePerson = reads.Begin(ReadCause.ThePerson, true);
        var theWatcher = reads.Begin(ReadCause.TheProjectWatcher, true);

        reads.End(theWatcher);

        Assert.True(reads.Rereading);

        reads.End(thePerson);

        Assert.False(reads.Rereading);
    }

    [Fact]
    public void EndsTheReReadMarkOnlyWhenTheLatestReadOfThePersonEnds()
    {
        var reads = new ReadSequence();
        var theFirst = reads.Begin(ReadCause.ThePerson, true);
        var theSecond = reads.Begin(ReadCause.ThePerson, true);

        reads.End(theFirst);

        Assert.True(reads.Rereading);

        reads.End(theSecond);

        Assert.False(reads.Rereading);
    }

    [Fact]
    public void LandsTheAnswerOfAnEarlierReadWhileNoLaterAnswerHasLanded()
    {
        var reads = new ReadSequence();
        var theEarlier = reads.Begin(ReadCause.ThePerson, true);
        reads.Begin(ReadCause.TheProjectWatcher, true);

        Assert.True(reads.CanLand(theEarlier));
    }

    [Fact]
    public void NeverLandsAnAnswerOverTheAnswerOfALaterRead()
    {
        var reads = new ReadSequence();
        var theEarlier = reads.Begin(ReadCause.ThePerson, true);
        var theLater = reads.Begin(ReadCause.TheProjectWatcher, true);

        reads.Land(theLater);

        Assert.False(reads.CanLand(theEarlier));
    }

    [Fact]
    public void NamesOnlyTheReadThatBeganLastAsTheLatest()
    {
        var reads = new ReadSequence();
        var theEarlier = reads.Begin(ReadCause.ThePerson, true);
        var theLater = reads.Begin(ReadCause.TheProjectWatcher, true);

        Assert.False(reads.IsTheLatest(theEarlier));
        Assert.True(reads.IsTheLatest(theLater));
    }
}
