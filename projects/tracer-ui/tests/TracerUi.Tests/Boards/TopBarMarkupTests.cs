using Bunit;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Boards;
using TracerUi.Web.Components.Layout;
using TracerUi.Web.Startup;

namespace TracerUi.Tests.Boards;

/// <summary>The top bar as a browser draws it, and the pages that its Board and Doctor links lead to.</summary>
public sealed class TopBarMarkupTests : BunitContext
{
    private readonly TwoProjects projects = new();

    public TopBarMarkupTests()
    {
        projects.RegisterOn(Services);
        Services.AddSingleton(BindAddress.From([]));
    }

    [Fact]
    public void LeadsTheBoardLinkToTheBoardOfTheActiveProject()
    {
        projects.Selection.Select(projects.Second);

        var bar = Render<TopBar>();

        Assert.Equal(BoardFilterAddress.Of(projects.Second, BoardFilter.Everything), TheBoardLinkOf(bar));
    }

    [Fact]
    public void LeadsTheBoardLinkToTheBoardOfTheProjectThatTheTabSwitchesTo()
    {
        projects.Selection.Select(projects.Second);
        var bar = Render<TopBar>();

        projects.Selection.Select(projects.First);

        bar.WaitForAssertion(() => Assert.Equal(
            BoardFilterAddress.Of(projects.First, BoardFilter.Everything),
            TheBoardLinkOf(bar)));
    }

    [Fact]
    public void LeadsTheBoardLinkToTheBoardAddressThatNamesNoProjectWhileTheTabHoldsNone()
    {
        var bar = Render<TopBar>();

        Assert.Equal(BoardFilterAddress.Page, TheBoardLinkOf(bar));
    }

    [Fact]
    public void LeadsTheDoctorLinkToTheDoctorPageOfTheActiveProject()
    {
        projects.Selection.Select(projects.Second);

        var bar = Render<TopBar>();

        Assert.Equal($"doctor?project={Uri.EscapeDataString(projects.Second.Value)}", TheLinkOf(bar, "Doctor"));
    }

    [Fact]
    public void LeadsTheDoctorLinkToTheDoctorPageOfTheProjectThatTheTabSwitchesTo()
    {
        projects.Selection.Select(projects.Second);
        var bar = Render<TopBar>();

        projects.Selection.Select(projects.First);

        bar.WaitForAssertion(() => Assert.Equal(
            $"doctor?project={Uri.EscapeDataString(projects.First.Value)}",
            TheLinkOf(bar, "Doctor")));
    }

    [Fact]
    public void LeadsTheDoctorLinkToTheDoctorAddressThatNamesNoProjectWhileTheTabHoldsNone()
    {
        var bar = Render<TopBar>();

        Assert.Equal("doctor", TheLinkOf(bar, "Doctor"));
    }

    private static string? TheBoardLinkOf(IRenderedComponent<TopBar> bar) => TheLinkOf(bar, "Board");

    private static string? TheLinkOf(IRenderedComponent<TopBar> bar, string words) =>
        bar.FindAll("a.top-bar-link").Single(link => link.TextContent.Trim() == words).GetAttribute("href");

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
