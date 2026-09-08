using Bunit;
using Microsoft.AspNetCore.Components.Web;

namespace TracerUi.Tests.Boards;

/// <summary>
/// The press that the row tests build. The travels it names decide what every one of those tests
/// proves, so they are checked against the row that reads them.
/// </summary>
public sealed class APressTests : BunitContext
{
    [Fact]
    public void OpensNothingWhenAPressTravelsTheDistanceThatAPressOfADragTravels()
    {
        var opened = new List<MouseEventArgs>();
        var row = APressableRow.ThatReportsTo(this, opened);

        APress.DragsAcross(() => row.Find("tr"), APress.Plain);

        Assert.Empty(opened);
    }

    [Fact]
    public void OpensTheBeadWhenAPressTravelsOnlyTheDistanceThatAPressOfAClickTravels()
    {
        var opened = new List<MouseEventArgs>();
        var row = APressableRow.ThatReportsTo(this, opened);

        APress.TravelsAcross(
            () => row.Find("tr"), APress.Plain, APress.Beside(APress.Plain, APress.TheTravelOfAClick));

        Assert.Single(opened);
    }

    [Fact]
    public void CarriesTheButtonAndTheKeysOfAPressOnTheReleaseThatLandsBesideIt()
    {
        var press = new MouseEventArgs { Button = 1, AltKey = true, CtrlKey = true, MetaKey = true, ShiftKey = true };

        var release = APress.Beside(press, APress.TheTravelOfADrag);

        Assert.Equal(press.Button, release.Button);
        Assert.True(release.AltKey && release.CtrlKey && release.MetaKey && release.ShiftKey);
    }
}
