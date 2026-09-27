using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Boards;

public sealed class BoardFilterAddressTests
{
    private static readonly ProjectPath Project = ProjectPath.From(Path.Combine(Path.GetTempPath(), "second"));

    private static readonly string TheProjectInTheQuery = $"project={Uri.EscapeDataString(Project.Value)}";

    [Fact]
    public void NamesTheProjectAloneForTheFilterThatKeepsEveryBead()
    {
        Assert.Equal($"board?{TheProjectInTheQuery}", BoardFilterAddress.Of(Project, BoardFilter.Everything));
    }

    [Fact]
    public void NamesTheProjectAloneForTheBoardOfEverythingInAProject()
    {
        Assert.Equal($"board?{TheProjectInTheQuery}", BoardFilterAddress.OfEverythingIn(Project));
    }

    [Fact]
    public void GivesTheBoardPageAloneForTheBoardOfEverythingInNoProject()
    {
        Assert.Equal("board", BoardFilterAddress.OfEverythingIn(null));
    }

    [Fact]
    public void ReadsTheFilterThatKeepsEveryBeadFromAnAddressThatCarriesNoQuery()
    {
        Assert.Equal(BoardFilter.Everything, BoardFilterAddress.FilterIn("http://localhost/board"));
    }

    [Fact]
    public void NamesTheProjectFirstAndThenEveryPartThatStatesSomethingInTheQuery()
    {
        var filter = BoardFilter.Everything with { Type = "bug", Label = "human", RequiresNoDemoLine = true };

        Assert.Equal(
            $"board?{TheProjectInTheQuery}&type=bug&label=human&no-demo=true",
            BoardFilterAddress.Of(Project, filter));
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

        Assert.Equal(filter, BoardFilterAddress.FilterIn("http://localhost/" + BoardFilterAddress.Of(Project, filter)));
    }

    [Fact]
    public void ReadsBackTheProjectThatItWroteIntoAnAddress()
    {
        var address = "http://localhost/" + BoardFilterAddress.Of(Project, BoardFilter.Everything with { Type = "bug" });

        Assert.Equal(new ProjectInTheAddress.Named(Project), ProjectInTheAddress.Of(address));
    }

    [Fact]
    public void KeepsATextThatHoldsTheCharactersOfAQueryWholeThroughTheAddress()
    {
        var filter = BoardFilter.Everything with { Text = "a=b&c d" };

        Assert.Equal("a=b&c d", BoardFilterAddress.FilterIn("/" + BoardFilterAddress.Of(Project, filter)).Text);
    }

    [Fact]
    public void KeepsEveryBeadWhenTheQueryNamesAPartThatTheFilterDoesNotHave()
    {
        Assert.Equal(BoardFilter.Everything, BoardFilterAddress.FilterIn("/board?colour=red"));
    }
}
