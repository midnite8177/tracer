using AngleSharp.Dom;
using Bunit;
using Bunit.TestDoubles;
using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using TracerUi.Web.Components.Layout;
using DetailPage = TracerUi.Web.Components.Pages.Detail;

namespace TracerUi.Tests.Boards;

/// <summary>The detail page as a browser draws it, and the project that its own address names.</summary>
public sealed class DetailAddressMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string TheBeadOfTheSecondProject =
        """[{"id": "b-7", "title": "Pick a hosting plan", "status": "open"}]""";

    private const string TheTitleOfThatBead = "Pick a hosting plan";

    private const string TheOtherBeadOfTheSecondProject =
        """[{"id": "b-9", "title": "Book the venue", "status": "open"}]""";

    private const string TheTitleOfTheOtherBeadOfTheSecondProject = "Book the venue";

    private const string TheBeadOfTheFirstProject =
        """[{"id": "b-7", "title": "Name the release", "status": "open"}]""";

    private const string TheTitleOfTheBeadOfTheFirstProject = "Name the release";

    private const string TheOtherBeadOfTheFirstProject =
        """[{"id": "b-9", "title": "Write the release notes", "status": "open"}]""";

    private const string TheTitleOfTheOtherBeadOfTheFirstProject = "Write the release notes";

    private const string TheOtherBeadOfTheFirstProjectAtPriorityTwo =
        """[{"id": "b-9", "title": "Write the release notes", "issue_type": "task", "priority": 2, "status": "open"}]""";

    private readonly TwoProjects projects = new();

    [Fact]
    public void ReadsTheBeadOfTheProjectThatItsAddressNamesInATabThatHoldsNoProjectYet()
    {
        var page = ThePageAt(TheAddressOfTheBead);

        Assert.Contains(TheTitleOfThatBead, page.Find("h1").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void MakesTheProjectThatItsAddressNamesTheActiveOne()
    {
        ThePageAt(TheAddressOfTheBead);

        Assert.Equal(projects.Second, projects.Selection.Current);
    }

    [Fact]
    public void KeepsTheProjectThatTheTabHoldsWhenTheAddressNamesNone()
    {
        var page = ThePageAt("bead/b-7", theActiveProject: projects.Second);

        Assert.Equal(projects.Second, projects.Selection.Current);
        Assert.Contains(TheTitleOfThatBead, page.Find("h1").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void ReplacesAnAddressThatNamesNoProjectWithOneThatNamesTheProjectOfTheTab()
    {
        ThePageAt("bead/b-7", theActiveProject: projects.Second);

        Assert.EndsWith(TheAddressOfTheBead, TheAddress(), StringComparison.Ordinal);
        Assert.True(TheLastNavigationReplacedItsHistoryEntry());
    }

    [Fact]
    public void AsksThePersonToPickAProjectWhenNeitherTheAddressNorTheTabNamesOne()
    {
        var page = ThePageAt("bead/b-7");

        Assert.Contains(NoActiveProject.Ask, page.Markup, StringComparison.Ordinal);
        Assert.DoesNotContain(TheTitleOfThatBead, page.Markup, StringComparison.Ordinal);
        Assert.EndsWith("bead/b-7", TheAddress(), StringComparison.Ordinal);
    }

    [Fact]
    public void SaysThatTheAddressNamesNoProjectItCanReadAndReadsTheBeadOfNoOtherProject()
    {
        var page = ThePageAt("bead/b-7?project=garbage", theActiveProject: projects.Second);

        Assert.Contains("garbage", page.Find("p.bead-message").TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain(TheTitleOfThatBead, page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void SaysThatTheProjectOfItsAddressLeftTheRegistryAndReadsTheBeadOfNoOtherProject()
    {
        projects.Forget(projects.Second);

        var page = ThePageAt(TheAddressOfTheBead, theActiveProject: projects.First);

        Assert.Contains("second", page.Find("p.bead-message").TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain(TheTitleOfThatBead, page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void LeadsBackToTheBoardAddressThatNamesNoProjectWhenTheProjectOfItsAddressLeftTheRegistry()
    {
        projects.Forget(projects.Second);

        var page = ThePageAt(TheAddressOfTheBead, theActiveProject: projects.First);

        Assert.Equal(BoardFilterAddress.Page, page.Find(".bead-head a").GetAttribute("href"));
    }

    [Fact]
    public void WalksToTheBoardOfThePickedProjectAsANewHistoryEntry()
    {
        ThePageAt(TheAddressOfTheBead);

        APick.Of(this, projects.First);

        Assert.EndsWith(BoardFilterAddress.Of(projects.First, BoardFilter.Everything), TheAddress(), StringComparison.Ordinal);
        Assert.False(TheLastNavigationReplacedItsHistoryEntry());
    }

    [Fact]
    public void ReadsTheBeadOfTheSameIdInTheProjectThatANewAddressNames()
    {
        var page = ThePageAt(TheAddressOfTheBead);
        projects.Bd
            .PrintsIn(projects.First.Value, "show b-7 --json", TheBeadOfTheFirstProject)
            .PrintsIn(projects.First.Value, "comments b-7 --json", "[]");

        Navigation.NavigateTo(TheAddressInTheFirstProjectOf("b-7"));

        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfTheBeadOfTheFirstProject, page.Find("h1").TextContent, StringComparison.Ordinal));
        Assert.Equal(1, projects.Bd.Runs(projects.First.Value, "show b-7 --json"));
        Assert.Equal(1, projects.Bd.Runs(projects.Second.Value, "show b-7 --json"));
        Assert.Equal(projects.First, projects.Selection.Current);
    }

    [Fact]
    public void ReadsAnotherBeadOnceInTheProjectThatANewAddressNames()
    {
        var page = ThePageAt(TheAddressOfTheBead);
        projects.Bd
            .PrintsIn(projects.First.Value, "show b-9 --json", TheOtherBeadOfTheFirstProject)
            .PrintsIn(projects.First.Value, "comments b-9 --json", "[]");

        TheRouterWalks(page, TheAddressInTheFirstProjectOf("b-9"), "b-9");

        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfTheOtherBeadOfTheFirstProject, page.Find("h1").TextContent, StringComparison.Ordinal));
        Assert.Equal(1, projects.Bd.Runs(projects.First.Value, "show b-9 --json"));
        Assert.Equal(0, projects.Bd.Runs(projects.First.Value, "show b-7 --json"));
        Assert.Equal(0, projects.Bd.Runs(projects.Second.Value, "show b-9 --json"));
    }

    [Fact]
    public void ReadsAnotherBeadOnceInTheProjectThatANewAddressNamesWhenTheRouterHandsThePageItsIdFirst()
    {
        var page = ThePageBehindARouter();
        projects.Bd
            .PrintsIn(projects.First.Value, "show b-9 --json", TheOtherBeadOfTheFirstProject)
            .PrintsIn(projects.First.Value, "comments b-9 --json", "[]");

        Navigation.NavigateTo(TheAddressInTheFirstProjectOf("b-9"));

        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfTheOtherBeadOfTheFirstProject, page.Find("h1").TextContent, StringComparison.Ordinal));
        Assert.Equal(1, projects.Bd.Runs(projects.First.Value, "show b-9 --json"));
        Assert.Equal(0, projects.Bd.Runs(projects.Second.Value, "show b-9 --json"));
    }

    [Fact]
    public void ReadsTheBeadOnceForEachAddressThatWalksBetweenTheBeadsOfTwoProjects()
    {
        var page = ThePageBehindARouter();
        projects.Bd
            .PrintsIn(projects.First.Value, "show b-9 --json", TheOtherBeadOfTheFirstProject)
            .PrintsIn(projects.First.Value, "comments b-9 --json", "[]")
            .PrintsIn(projects.First.Value, "show b-7 --json", TheBeadOfTheFirstProject)
            .PrintsIn(projects.First.Value, "comments b-7 --json", "[]");

        Navigation.NavigateTo(TheAddressInTheFirstProjectOf("b-9"));
        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfTheOtherBeadOfTheFirstProject, page.Find("h1").TextContent, StringComparison.Ordinal));
        Navigation.NavigateTo(TheAddressOfTheBead);
        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfThatBead, page.Find("h1").TextContent, StringComparison.Ordinal));
        Navigation.NavigateTo(TheAddressInTheFirstProjectOf("b-7"));
        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfTheBeadOfTheFirstProject, page.Find("h1").TextContent, StringComparison.Ordinal));

        Assert.Equal(1, projects.Bd.Runs(projects.First.Value, "show b-9 --json"));
        Assert.Equal(2, projects.Bd.Runs(projects.Second.Value, "show b-7 --json"));
        Assert.Equal(1, projects.Bd.Runs(projects.First.Value, "show b-7 --json"));
        Assert.Equal(projects.First, projects.Selection.Current);
    }

    [Fact]
    public void ReadsTheBeadOnceWhenItNamesTheProjectOfTheTabInAnAddressThatNamesNone()
    {
        var page = ThePageAt("bead/b-7", theActiveProject: projects.Second);

        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfThatBead, page.Find("h1").TextContent, StringComparison.Ordinal));
        Assert.Equal(1, projects.Bd.Runs(projects.Second.Value, "show b-7 --json"));
    }

    [Theory]
    [InlineData("needs-you")]
    [InlineData("")]
    [InlineData("board")]
    public void LeavesTheAddressOfTheNextPageAloneWhenAPersonWalksAwayFromTheBeadPage(string nextPage)
    {
        ThePageAt(TheAddressOfTheBead);

        Navigation.NavigateTo(nextPage);

        Assert.Equal(nextPage, Navigation.ToBaseRelativePath(TheAddress()));
    }

    [Fact]
    public void KeepsTheBeadOfTheOldProjectOffTheScreenWhenBdAnswersItAfterANewAddressNamedAnotherProject()
    {
        projects.Bd.Holds("show b-7 --json");
        var page = ThePageAt(TheAddressOfTheBead);
        projects.Bd
            .PrintsIn(projects.First.Value, "show b-9 --json", TheOtherBeadOfTheFirstProject)
            .PrintsIn(projects.First.Value, "comments b-9 --json", "[]");

        TheRouterWalks(page, TheAddressInTheFirstProjectOf("b-9"), "b-9");
        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfTheOtherBeadOfTheFirstProject, page.Find("h1").TextContent, StringComparison.Ordinal));

        projects.Bd.Answers("show b-7 --json", TheBeadOfTheSecondProject);

        page.WaitForAssertion(() => Assert.Equal(1, projects.Bd.Runs(projects.Second.Value, "comments b-7 --json")));
        Assert.Contains(TheTitleOfTheOtherBeadOfTheFirstProject, page.Find("h1").TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain(TheTitleOfThatBead, page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void KeepsTheOldBeadOffTheScreenWhenBdAnswersItAfterANewAddressNamedAnotherBeadOfTheSameProject()
    {
        projects.Bd.Holds("show b-7 --json");
        var page = ThePageAt(TheAddressOfTheBead);
        projects.Bd
            .PrintsIn(projects.Second.Value, "show b-9 --json", TheOtherBeadOfTheSecondProject)
            .PrintsIn(projects.Second.Value, "comments b-9 --json", "[]");

        TheRouterWalks(page, TheAddressIn(projects.Second, "b-9"), "b-9");
        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfTheOtherBeadOfTheSecondProject, page.Find("h1").TextContent, StringComparison.Ordinal));

        var commentReads = projects.Bd.Runs(projects.Second.Value, "comments b-7 --json");
        projects.Bd.Answers("show b-7 --json", TheBeadOfTheSecondProject);

        page.WaitForAssertion(() =>
            Assert.Equal(commentReads + 1, projects.Bd.Runs(projects.Second.Value, "comments b-7 --json")));
        Assert.Contains(TheTitleOfTheOtherBeadOfTheSecondProject, page.Find("h1").TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain(TheTitleOfThatBead, page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void TitlesTheTabWithTheIdOnceANewAddressNamesNoProjectItCanRead()
    {
        var page = ThePageAt(TheAddressOfTheBead);
        var head = TheHeadOfThePage();
        page.WaitForAssertion(() => Assert.Equal(TheTitleOfThatBead, head.Find("title").TextContent));

        Navigation.NavigateTo("bead/b-7?project=garbage");

        page.WaitForAssertion(() => Assert.Equal("b-7", head.Find("title").TextContent));
    }

    [Fact]
    public void KeepsTheLateAnswerOfTheBeadOffAPageWhoseNewAddressNamesNoProjectItCanRead()
    {
        projects.Bd.Holds("show b-7 --json");
        var page = ThePageAt(TheAddressOfTheBead);
        var head = TheHeadOfThePage();
        Navigation.NavigateTo("bead/b-7?project=garbage");
        page.WaitForAssertion(() =>
            Assert.Contains("garbage", page.Find("p.bead-message").TextContent, StringComparison.Ordinal));

        var commentReads = projects.Bd.Runs(projects.Second.Value, "comments b-7 --json");
        projects.Bd.Answers("show b-7 --json", TheBeadOfTheSecondProject);

        page.WaitForAssertion(() =>
            Assert.Equal(commentReads + 1, projects.Bd.Runs(projects.Second.Value, "comments b-7 --json")));
        Assert.Equal("b-7", head.Find("title").TextContent);
        Assert.DoesNotContain(TheTitleOfThatBead, page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void KeepsTheReReadMarkOfTheNewProjectWhenBdAnswersTheReadOfTheProjectThatThePageLeft()
    {
        projects.Bd.Holds("show b-7 --json");
        var page = ThePageAt(TheAddressOfTheBead);
        projects.Bd
            .DeclaresEveryWrite()
            .PrintsIn(projects.First.Value, "show b-9 --json", TheOtherBeadOfTheFirstProjectAtPriorityTwo)
            .PrintsIn(projects.First.Value, "comments b-9 --json", "[]")
            .Prints("update b-9 --priority 1", string.Empty);
        TheRouterWalks(page, TheAddressInTheFirstProjectOf("b-9"), "b-9");
        page.WaitForAssertion(() => ThePress(page, "Priority, p2"));

        projects.Bd.Holds("show b-9 --json");
        ThePress(page, "Priority, p2").Click();
        ThePick(page, "p1").Click();
        projects.Clock.Advance(WorkingMark.WaitBeforeShowing);
        page.WaitForAssertion(() => Assert.Single(page.FindAll(".re-read-mark")));
        projects.Clock.Advance(WorkingMark.Floor);
        var renders = page.RenderCount;

        projects.Bd.Answers("show b-7 --json", TheBeadOfTheSecondProject);

        page.WaitForState(() => page.RenderCount > renders);
        Assert.Single(page.FindAll(".re-read-mark"));
    }

    private NavigationManager Navigation => Services.GetRequiredService<NavigationManager>();

    // HeadOutlet asks the browser for the title it replaces, and a test has no browser to answer.
    private IRenderedComponent<HeadOutlet> TheHeadOfThePage()
    {
        JSInterop.Mode = JSRuntimeMode.Loose;
        return Render<HeadOutlet>();
    }

    private string TheAddress() => Navigation.Uri;

    private void TheRouterWalks(IRenderedComponent<DetailPage> page, string address, string id)
    {
        Navigation.NavigateTo(address);
        page.Render(parameters => parameters.Add(detail => detail.Id, id));
    }

    private static string TheAddressIn(ProjectPath project, string id) =>
        $"bead/{id}?project={Uri.EscapeDataString(project.Value)}";

    private string TheAddressInTheFirstProjectOf(string id) => TheAddressIn(projects.First, id);

    private string TheAddressOfTheBead => TheAddressIn(projects.Second, "b-7");

    private static IElement ThePress(IRenderedComponent<DetailPage> page, string accessibleName) =>
        page.Find($".bead-fact-value button[aria-label='{accessibleName}']");

    private static IElement ThePick(IRenderedComponent<DetailPage> page, string text) =>
        page.FindAll(".bead-fact-picker .bead-fact-choice")
            .Single(entry => string.Equals(
                entry.QuerySelector(".bead-fact-words")?.TextContent.Trim(), text, StringComparison.Ordinal));

    private bool TheLastNavigationReplacedItsHistoryEntry() =>
        Navigation is BunitNavigationManager navigation
        && navigation.History.First().Options.ReplaceHistoryEntry;

    private IRenderedComponent<DetailPage> ThePageAt(string address) =>
        ThePageAt(address, theActiveProject: null);

    // The detail page at this address, in a tab that holds this project or no project at all. Only
    // the second project holds the bead, so a page that reads another project shows nothing.
    private IRenderedComponent<DetailPage> ThePageAt(string address, ProjectPath? theActiveProject)
    {
        TheServicesOfThePageAt(address, theActiveProject);

        return Render<DetailPage>(parameters => parameters.Add(page => page.Id, "b-7"));
    }

    // The detail page of the bead of the second project, behind a router that hands the page the id
    // of each bead address that names another id, as Blazor's router does.
    private IRenderedComponent<DetailPage> ThePageBehindARouter()
    {
        TheServicesOfThePageAt(TheAddressOfTheBead, theActiveProject: null);
        IRenderedComponent<DetailPage>? routed = null;
        Navigation.LocationChanged += (_, changed) =>
        {
            var path = Navigation.ToBaseRelativePath(changed.Location).Split('?')[0];
            if (routed is null || !path.StartsWith("bead/", StringComparison.Ordinal))
            {
                return;
            }

            var id = Uri.UnescapeDataString(path["bead/".Length..]);
            if (!string.Equals(id, routed.Instance.Id, StringComparison.Ordinal))
            {
                routed.Render(parameters => parameters.Add(page => page.Id, id));
            }
        };
        routed = Render<DetailPage>(parameters => parameters.Add(page => page.Id, "b-7"));

        return routed;
    }

    private void TheServicesOfThePageAt(string address, ProjectPath? theActiveProject)
    {
        projects.Bd
            .PrintsIn(projects.Second.Value, "show b-7 --json", TheBeadOfTheSecondProject)
            .PrintsIn(projects.Second.Value, "comments b-7 --json", "[]")
            .PrintsIn(projects.Second.Value, ListCommand, TheBeadOfTheSecondProject)
            .PrintsIn(projects.First.Value, ListCommand, "[]");
        if (theActiveProject is not null)
        {
            projects.Selection.Select(theActiveProject);
        }

        projects.RegisterOn(Services);
        Services.AddSingleton(new BeadDetailReader(projects.Adapter, new BacklogReader(projects.Adapter)));

        Navigation.NavigateTo(address);
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
