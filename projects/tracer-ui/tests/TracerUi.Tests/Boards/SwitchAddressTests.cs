using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using TracerUi.Web.Components.Pages;

namespace TracerUi.Tests.Boards;

public sealed class SwitchAddressTests
{
    private static readonly ProjectPath AProject = ProjectPath.From(Path.GetTempPath());

    [Fact]
    public void WalksNowhereFromAPageThatSaidNothing()
    {
        Assert.Null(new SwitchAddress().For(AProject));
    }

    [Fact]
    public void WalksWhereThePageOnTheScreenSaid()
    {
        var switches = new SwitchAddress();

        switches.WalkTo(DoctorAddress.Of);

        Assert.Equal(DoctorAddress.Of(AProject), switches.For(AProject));
    }

    [Fact]
    public void WalksNowhereOnceThePageThatSaidWhereIsGone()
    {
        var switches = new SwitchAddress();

        switches.WalkTo(DoctorAddress.Of).Dispose();

        Assert.Null(switches.For(AProject));
    }

    [Fact]
    public void KeepsTheWalkOfTheArrivingPageWhenThePageItLeftGoesAfterIt()
    {
        var switches = new SwitchAddress();
        var leaving = switches.WalkTo(DoctorAddress.Of);

        switches.WalkTo(BoardFilterAddress.OfEverythingIn);
        leaving.Dispose();

        Assert.Equal(BoardFilterAddress.OfEverythingIn(AProject), switches.For(AProject));
    }
}
