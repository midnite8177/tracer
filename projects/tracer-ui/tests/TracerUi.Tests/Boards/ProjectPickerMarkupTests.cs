using Bunit;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Web.Components.Layout;
using TracerUi.Web.Components.Pages;
using TracerUi.Web.Startup;

namespace TracerUi.Tests.Boards;

public sealed class ProjectPickerMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private readonly TwoProjects projects = new();

    public ProjectPickerMarkupTests()
    {
        projects.Bd
            .PrintsIn(projects.First.Value, ListCommand, "[]")
            .PrintsIn(projects.Second.Value, ListCommand, "[]");
        projects.RegisterOn(Services);
        Services.AddSingleton(new NeedsYouReader(projects.Catalog, projects.Backlogs));
        Services.AddSingleton(BindAddress.From([]));
    }

    [Fact]
    public void StaysOnTheNeedsYouViewAndLeadsTheBoardAndDoctorLinksToThePickedProject()
    {
        projects.Selection.Select(projects.Second);
        Navigation.NavigateTo("needs-you");
        var view = Render<NeedsYou>();
        var bar = Render<TopBar>();

        bar.Find("select.project-picker").Change(projects.First.Value);

        Assert.Equal("needs-you", Navigation.ToBaseRelativePath(Navigation.Uri));
        Assert.Equal("Needs you", view.Find("h1").TextContent);
        AssertTheLinksNameTheFirstProject(bar);
    }

    [Fact]
    public void StaysOnTheListOfProjectsAndLeadsTheBoardAndDoctorLinksToThePickedProject()
    {
        projects.Selection.Select(projects.Second);
        Navigation.NavigateTo(string.Empty);
        var home = Render<Home>();
        var bar = Render<TopBar>();

        bar.Find("select.project-picker").Change(projects.First.Value);

        Assert.Equal(string.Empty, Navigation.ToBaseRelativePath(Navigation.Uri));
        Assert.Equal("Projects", home.Find("h1").TextContent);
        AssertTheLinksNameTheFirstProject(bar);
    }

    [Fact]
    public void CallsTheBrowserForNothingBeforeOrAfterAPickInATabThatHeldNoProject()
    {
        Navigation.NavigateTo("needs-you");
        Render<NeedsYou>();
        var bar = Render<TopBar>();

        Assert.Empty(JSInterop.Invocations);

        bar.Find("select.project-picker").Change(projects.First.Value);

        AssertTheLinksNameTheFirstProject(bar);
        Assert.Empty(JSInterop.Invocations);
    }

    private void AssertTheLinksNameTheFirstProject(IRenderedComponent<TopBar> bar)
    {
        Assert.Equal(projects.First, projects.Selection.Current);
        bar.WaitForAssertion(() => Assert.Equal(
            BoardFilterAddress.Of(projects.First, BoardFilter.Everything),
            TheLinkOf(bar, "Board")));
        Assert.Equal(DoctorAddress.Of(projects.First), TheLinkOf(bar, "Doctor"));
    }

    private NavigationManager Navigation => Services.GetRequiredService<NavigationManager>();

    private static string? TheLinkOf(IRenderedComponent<TopBar> bar, string words) =>
        bar.FindAll("a.top-bar-link").Single(link => link.TextContent.Trim() == words).GetAttribute("href");

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
