using Bunit;
using TracerUi.Core.Boards;
using TracerUi.Web.Components.Layout;
using TracerUi.Web.Components.Pages;

namespace TracerUi.Tests.Boards;

public sealed class HomeMarkupTests : BunitContext
{
    private readonly TwoProjects projects = new();

    public HomeMarkupTests()
    {
        projects.RegisterOn(Services);
    }

    [Fact]
    public void LinksEachProjectToItsBoard()
    {
        var home = Render<Home>();

        Assert.Equal(
            [BoardFilterAddress.OfEverythingIn(projects.First), BoardFilterAddress.OfEverythingIn(projects.Second)],
            home.FindAll("ul.project-list a").Select(link => link.GetAttribute("href")));
    }

    [Fact]
    public void MarksTheProjectThatTheTabSwitchesTo()
    {
        projects.Selection.Select(projects.Second);
        var home = Render<Home>();

        projects.Selection.Select(projects.First);

        home.WaitForAssertion(() => Assert.Equal(
            "first",
            home.Find("li.project-row-active a").TextContent.Trim()));
    }

    [Fact]
    public void ShowsNoActiveProjectInAFreshTabAtTheRoot()
    {
        var home = Render<Home>();
        var picker = Render<ProjectPicker>();

        Assert.Equal("none", home.Find("p.project-active strong").TextContent);
        Assert.Empty(home.FindAll("li.project-row-active"));
        Assert.Equal("Select a project", picker.Find("select.project-picker option").TextContent);
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
