using Bunit;
using Bunit.TestDoubles;
using Microsoft.AspNetCore.Components;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using TracerUi.Web.Components.Pages;

namespace TracerUi.Tests.Boards;

/// <summary>The doctor page as a browser draws it, and the project that its own address names.</summary>
public sealed class DoctorAddressMarkupTests : BunitContext
{
    private const string TheFirstVersion = "0.61.0";
    private const string TheSecondVersion = "0.62.0";

    private readonly TwoProjects projects = new();

    [Fact]
    public void ReportsTheBdOfTheProjectThatItsAddressNames()
    {
        var doctor = TheDoctorAt(DoctorAddress.Of(projects.Second), theActiveProject: projects.First);

        doctor.WaitForAssertion(() => Assert.Equal(TheSecondVersion, TheVersionOn(doctor)));
        Assert.Equal(projects.Second.Value, doctor.Find("p.doctor-path").TextContent);
    }

    [Fact]
    public void ReplacesAnAddressThatNamesNoProjectWithOneThatNamesTheProjectOfTheTab()
    {
        var doctor = TheDoctorAt("doctor", theActiveProject: projects.Second);

        Assert.EndsWith(
            $"doctor?project={Uri.EscapeDataString(projects.Second.Value)}",
            TheAddress(),
            StringComparison.Ordinal);
        Assert.True(TheLastNavigationReplacedItsHistoryEntry());
        doctor.WaitForAssertion(() => Assert.Equal(TheSecondVersion, TheVersionOn(doctor)));
    }

    [Fact]
    public void AsksThePersonToPickAProjectWhenNeitherTheAddressNorTheTabNamesOne()
    {
        var doctor = TheDoctorAt("doctor", theActiveProject: null);

        Assert.Contains(NoActiveProject.Ask, doctor.Markup, StringComparison.Ordinal);
        Assert.Equal(string.Empty, TheVersionOn(doctor));
        Assert.Equal("doctor", Navigation.ToBaseRelativePath(TheAddress()));
    }

    [Fact]
    public void SaysThatTheProjectOfItsAddressLeftTheRegistryAndReportsNoBd()
    {
        projects.Forget(projects.Second);

        var doctor = TheDoctorAt(DoctorAddress.Of(projects.Second), theActiveProject: projects.First);

        Assert.Equal(
            "second is not in the registry any more, so this address names no project whose bd it can report.",
            doctor.Find("p.doctor-message").TextContent);
        Assert.Equal(string.Empty, TheVersionOn(doctor));
        Assert.Empty(doctor.FindAll("table"));
        Assert.Equal(0, projects.Bd.Runs(projects.First.Value, "version"));
    }

    [Fact]
    public void ReportsTheBdOfTheProjectThatANewAddressNames()
    {
        var doctor = TheDoctorAt(DoctorAddress.Of(projects.First), theActiveProject: null);
        doctor.WaitForAssertion(() => Assert.Equal(TheFirstVersion, TheVersionOn(doctor)));

        Navigation.NavigateTo(DoctorAddress.Of(projects.Second));

        doctor.WaitForAssertion(() => Assert.Equal(TheSecondVersion, TheVersionOn(doctor)));
        Assert.Equal(projects.Second.Value, doctor.Find("p.doctor-path").TextContent);
        Assert.Equal(projects.Second, projects.Selection.Current);
    }

    [Fact]
    public void ReportsTheBdOfEachProjectAsTheAddressWalksBetweenTheDoctorPagesOfTwoProjects()
    {
        var doctor = TheDoctorAt(DoctorAddress.Of(projects.First), theActiveProject: null);
        doctor.WaitForAssertion(() => Assert.Equal(TheFirstVersion, TheVersionOn(doctor)));

        Navigation.NavigateTo(DoctorAddress.Of(projects.Second));
        doctor.WaitForAssertion(() => Assert.Equal(TheSecondVersion, TheVersionOn(doctor)));
        Navigation.NavigateTo(DoctorAddress.Of(projects.First));
        doctor.WaitForAssertion(() => Assert.Equal(TheFirstVersion, TheVersionOn(doctor)));

        // The probe of bd holds for the life of the app and takes no invalidation, so the walk back
        // runs no second probe. The counts show one probe per project, not one per address.
        Assert.Equal(projects.First.Value, doctor.Find("p.doctor-path").TextContent);
        Assert.Equal(1, projects.Bd.Runs(projects.First.Value, "version"));
        Assert.Equal(1, projects.Bd.Runs(projects.Second.Value, "version"));
        Assert.Equal(projects.First, projects.Selection.Current);
    }

    [Fact]
    public void WalksToTheDoctorPageOfThePickedProjectAsANewHistoryEntry()
    {
        var doctor = TheDoctorAt(DoctorAddress.Of(projects.Second), theActiveProject: null);

        APick.Of(this, projects.First);

        doctor.WaitForAssertion(() => Assert.Equal(TheFirstVersion, TheVersionOn(doctor)));
        Assert.EndsWith(
            $"doctor?project={Uri.EscapeDataString(projects.First.Value)}",
            TheAddress(),
            StringComparison.Ordinal);
        Assert.False(TheLastNavigationReplacedItsHistoryEntry());
    }

    [Theory]
    [InlineData("needs-you")]
    [InlineData("")]
    public void LeavesTheAddressOfTheNextPageAloneWhenAPersonWalksAwayFromTheDoctorPage(string nextPage)
    {
        TheDoctorAt(DoctorAddress.Of(projects.Second), theActiveProject: null);

        Navigation.NavigateTo(nextPage);

        Assert.Equal(nextPage, Navigation.ToBaseRelativePath(TheAddress()));
    }

    private static string TheVersionOn(IRenderedComponent<Doctor> doctor) =>
        doctor.FindAll("strong.machine-text").Select(version => version.TextContent).SingleOrDefault(string.Empty);

    private NavigationManager Navigation => Services.GetRequiredService<NavigationManager>();

    private string TheAddress() => Navigation.Uri;

    private bool TheLastNavigationReplacedItsHistoryEntry() =>
        Navigation is BunitNavigationManager navigation
        && navigation.History.First().Options.ReplaceHistoryEntry;

    private IRenderedComponent<Doctor> TheDoctorAt(string address, ProjectPath? theActiveProject)
    {
        projects.Bd
            .PrintsIn(projects.First.Value, "version", $"bd version {TheFirstVersion}")
            .PrintsIn(projects.Second.Value, "version", $"bd version {TheSecondVersion}");
        if (theActiveProject is not null)
        {
            projects.Selection.Select(theActiveProject);
        }

        projects.RegisterOn(Services);
        Navigation.NavigateTo(address);

        return Render<Doctor>();
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
