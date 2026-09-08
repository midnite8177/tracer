using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

public sealed class BoardFilterAddressTests
{
    [Fact]
    public void GivesThePlainBoardAddressForTheFilterThatKeepsEveryBead()
    {
        Assert.Equal("board", BoardFilterAddress.Of(BoardFilter.Everything));
    }

    [Fact]
    public void ReadsTheFilterThatKeepsEveryBeadFromAnAddressThatCarriesNoQuery()
    {
        Assert.Equal(BoardFilter.Everything, BoardFilterAddress.FilterIn("http://localhost/board"));
    }

    [Fact]
    public void NamesEveryPartThatStatesSomethingInTheQuery()
    {
        var filter = BoardFilter.Everything with { Type = "bug", Label = "human", RequiresNoDemoLine = true };

        Assert.Equal("board?type=bug&label=human&no-demo=true", BoardFilterAddress.Of(filter));
    }

    [Fact]
    public void ReadsBackEveryPartThatItWroteIntoAnAddress()
    {
        var filter = new BoardFilter(
            Status: StoredStatus.Closed,
            Type: "bug",
            Priority: "2",
            Label: "needs a person",
            Epic: "x-9",
            Text: "board & filter",
            RequiresHumanLabel: true,
            RequiresNoDemoLine: true,
            ShowDeferred: true,
            ShowClosed: true);

        Assert.Equal(filter, BoardFilterAddress.FilterIn("http://localhost/" + BoardFilterAddress.Of(filter)));
    }

    [Fact]
    public void KeepsATextThatHoldsTheCharactersOfAQueryWholeThroughTheAddress()
    {
        var filter = BoardFilter.Everything with { Text = "a=b&c d" };

        Assert.Equal("a=b&c d", BoardFilterAddress.FilterIn("/" + BoardFilterAddress.Of(filter)).Text);
    }

    [Fact]
    public void KeepsEveryBeadWhenTheQueryNamesAPartThatTheFilterDoesNotHave()
    {
        Assert.Equal(BoardFilter.Everything, BoardFilterAddress.FilterIn("/board?colour=red"));
    }
}
