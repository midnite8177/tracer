using Bunit;
using AngleSharp.Dom;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Boards;
using TracerUi.Web.Components.Layout;
using NeedsYouPage = TracerUi.Web.Components.Pages.NeedsYou;

namespace TracerUi.Tests.Boards;

/// <summary>
/// The needs-you view as a browser draws it: what a press on a row does, and which project the
/// bead of that row opens in.
/// </summary>
public sealed class NeedsYouMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string OneBeadOfTheFirstProject =
        """[{"id": "a-1", "title": "Decide the licence", "status": "open", "labels": ["human"]}]""";

    private const string OneBeadOfTheSecondProject =
        """[{"id": "b-7", "title": "Pick a hosting plan", "status": "open", "labels": ["human"]}]""";

    // The bead that the second project holds, which every press of these tests opens.
    private const string TheBeadOfTheSecondProject = "Pick a hosting plan";

    private readonly TwoProjects projects = new();

    [Fact]
    public void OpensTheBeadOfARowInANewTabOnTheProjectThatHoldsItWhenThePressCarriesTheMetaKey()
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var view = TheViewOfTwoProjects();

        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        Assert.Equal([TheAddressOfTheBead], ABrowser.TheAddressesOf(opened));
    }

    [Fact]
    public void StaysOnTheNeedsYouViewWhenAPressOnARowAsksForANewTab()
    {
        ABrowser.ThatOpensEveryTab(this);
        var view = TheViewOfTwoProjects();
        var where = ABrowser.TheAddressItStandsOn(this);

        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        Assert.Equal(where, ABrowser.TheAddressItStandsOn(this));
    }

    [Fact]
    public void OpensTheBeadOfARowInANewTabWhenTheMiddleButtonReleasesOnIt()
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var view = TheViewOfTwoProjects();

        TheRowOfTheBead(view)().MouseUp(APress.OfTheMiddleButton);

        Assert.Equal([TheAddressOfTheBead], ABrowser.TheAddressesOf(opened));
    }

    [Fact]
    public void OpensOneTabAloneWhenAPressOnTheTitleOfARowAsksForANewTab()
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var view = TheViewOfTwoProjects();

        TheTitleOfTheBead(view).Click(APress.CarryingTheMetaKey);

        Assert.Equal([TheAddressOfTheBead], ABrowser.TheAddressesOf(opened));
    }

    [Fact]
    public void OpensNoTabWhenAPressTravelsAcrossARowAndAsksForANewTab()
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var view = TheViewOfTwoProjects();

        APress.DragsAcross(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        Assert.Empty(ABrowser.TheAddressesOf(opened));
    }

    [Fact]
    public void OpensTheBeadOfARowWhenAPressOnItTravelsTheSmallDistanceOfAHandThatHoldsAMouse()
    {
        var view = TheViewOfTwoProjects();

        APress.TravelsAcross(
            TheRowOfTheBead(view), APress.Plain, APress.Beside(APress.Plain, APress.TheTravelOfAClick));

        Assert.EndsWith(TheAddressOfTheBead, ABrowser.TheAddressItStandsOn(this), StringComparison.Ordinal);
    }

    [Fact]
    public void StaysOnTheNeedsYouViewWhenAPressTravelsAcrossARowAndReleasesFarFromWhereItStarted()
    {
        var view = TheViewOfTwoProjects();
        var where = ABrowser.TheAddressItStandsOn(this);

        APress.DragsAcross(TheRowOfTheBead(view), APress.Plain);

        Assert.Equal(where, ABrowser.TheAddressItStandsOn(this));
    }

    [Fact]
    public void OpensTheBeadOfARowInThisTabOnTheProjectThatHoldsItWhenThePressCarriesNoKey()
    {
        var view = TheViewOfTwoProjects();

        APress.LandsOn(TheRowOfTheBead(view), APress.Plain);

        Assert.EndsWith(TheAddressOfTheBead, ABrowser.TheAddressItStandsOn(this), StringComparison.Ordinal);
    }

    [Fact]
    public void SaysThatTheProjectOfARowLeftTheRegistryAndOpensNoTab()
    {
        var opened = ABrowser.ThatOpensEveryTab(this);
        var view = TheViewOfTwoProjects();
        projects.Forget(projects.Second);

        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        Assert.Contains("second", view.Find("p.failure-message").TextContent, StringComparison.Ordinal);
        Assert.Empty(ABrowser.TheAddressesOf(opened));
    }

    [Fact]
    public void SaysThatTheBrowserRefusedTheTabWhenAPressOnARowAsksForOneAndNoTabOpens()
    {
        ABrowser.ThatRefusesEveryTab(this);
        var view = TheViewOfTwoProjects();

        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        Assert.Contains("popups", TheNewTabRefusal.On(view), StringComparison.Ordinal);
    }

    [Fact]
    public void SaysNothingAboutANewTabWhenTheBrowserOpensTheOneThatARowAsksFor()
    {
        ABrowser.ThatOpensEveryTab(this);
        var view = TheViewOfTwoProjects();

        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        Assert.Empty(TheNewTabRefusal.EveryOneOn(view));
    }

    [Fact]
    public void StopsTheRefusalOfATabWhenALaterPressOnARowOpensOne()
    {
        var browser = ABrowser.ThatRefusesEveryTab(this);
        var view = TheViewOfTwoProjects();
        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        browser.SetResult(true);
        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        Assert.Empty(TheNewTabRefusal.EveryOneOn(view));
    }

    [Fact]
    public void StopsTheRefusalOfATabWhenALaterPressLandsOnARowWhoseProjectLeftTheRegistry()
    {
        ABrowser.ThatRefusesEveryTab(this);
        var view = TheViewOfTwoProjects();
        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        projects.Forget(projects.Second);
        APress.LandsOn(TheRowOfTheBead(view), APress.CarryingTheMetaKey);

        Assert.Empty(TheNewTabRefusal.EveryOneOn(view));
    }

    [Fact]
    public void DrawsTheRowOfEveryBeadAsAPressableRowThatHoldsTheTitleOfThatBead()
    {
        var view = TheViewOfTwoProjects();

        Assert.Equal(2, view.FindComponents<PressableRow>().Count);
        Assert.Equal(2, view.FindComponents<RowTitle>().Count);
    }

    private string TheAddressOfTheBead => $"bead/b-7?project={Uri.EscapeDataString(projects.Second.Value)}";

    private static Func<IElement> TheRowOfTheBead(IRenderedComponent<NeedsYouPage> view) =>
        () => view.FindAll("tr.needs-you-row")
            .Single(row => row.TextContent.Contains(TheBeadOfTheSecondProject, StringComparison.Ordinal));

    private static IElement TheTitleOfTheBead(IRenderedComponent<NeedsYouPage> view) =>
        view.FindAll("a.needs-you-title").Single(link => link.TextContent == TheBeadOfTheSecondProject);

    // The needs-you view of two projects, each with one bead that waits on a person. The first
    // project is the active one, so a row of the second one names another project than the view.
    private IRenderedComponent<NeedsYouPage> TheViewOfTwoProjects()
    {
        projects.Bd
            .PrintsIn(projects.First.Value, ListCommand, OneBeadOfTheFirstProject)
            .PrintsIn(projects.Second.Value, ListCommand, OneBeadOfTheSecondProject);
        projects.Selection.Select(projects.First);

        projects.RegisterOn(Services);
        Services.AddSingleton(new NeedsYouReader(projects.Catalog, projects.Backlogs));

        return Render<NeedsYouPage>();
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
