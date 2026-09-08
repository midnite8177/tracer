using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class IdSetTests
{
    [Fact]
    public void HoldsTheBeadsThatAPersonPickedAndNoOther()
    {
        var selection = new IdSet();

        selection.Toggle("x-1");
        selection.Toggle("x-2");

        Assert.True(selection.Holds("x-1"));
        Assert.True(selection.Holds("x-2"));
        Assert.False(selection.Holds("x-3"));
        Assert.Equal(2, selection.Count);
    }

    [Fact]
    public void TakesEveryBeadOfAGroupInOneAction()
    {
        var selection = new IdSet();

        selection.TakeAll(["x-1", "x-2", "x-3"]);

        Assert.Equal(3, selection.Count);
        Assert.True(selection.Holds("x-2"));
    }

    [Fact]
    public void TakesEveryBeadOfAGroupOnOnePressAndDropsThemOnTheNext()
    {
        var selection = new IdSet();

        selection.ToggleAll(["x-1", "x-2"]);

        Assert.True(selection.HoldsAll(["x-1", "x-2"]));

        selection.ToggleAll(["x-1", "x-2"]);

        Assert.True(selection.IsEmpty);
    }

    [Fact]
    public void TakesTheRestOfAGroupWhenTheSelectionHoldsOnlyAPartOfIt()
    {
        var selection = new IdSet();
        selection.Toggle("x-1");

        selection.ToggleAll(["x-1", "x-2"]);

        Assert.True(selection.HoldsAll(["x-1", "x-2"]));
    }

    [Fact]
    public void DropsEveryBeadOfAGroupWhenTheGroupIsAlreadyWhole()
    {
        var selection = new IdSet();
        selection.TakeAll(["x-1", "x-2"]);

        selection.DropAll(["x-1", "x-2"]);

        Assert.True(selection.IsEmpty);
    }

    [Fact]
    public void SaysThatItHoldsAWholeGroupOnlyWhenEveryBeadOfThatGroupIsInIt()
    {
        var selection = new IdSet();
        selection.TakeAll(["x-1", "x-2"]);

        Assert.True(selection.HoldsAll(["x-1", "x-2"]));
        Assert.False(selection.HoldsAll(["x-1", "x-3"]));
        Assert.False(selection.HoldsAll([]));
    }

    [Fact]
    public void DropsFromTheSelectionTheBeadsThatTheFilterTookOffTheBoard()
    {
        var selection = new IdSet();
        selection.TakeAll(["x-1", "x-2", "x-3"]);

        selection.KeepOnly(["x-1", "x-3"]);

        Assert.Equal(["x-1", "x-3"], selection.Ids.Order(StringComparer.Ordinal));
    }

    [Fact]
    public void HoldsNothingAfterAPersonClearsIt()
    {
        var selection = new IdSet();
        selection.TakeAll(["x-1", "x-2"]);

        selection.Clear();

        Assert.True(selection.IsEmpty);
    }
}
