using Bunit;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Factory;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Notifications;
using JidokaUi.Tests.Boards;
using JidokaUi.Web.Components.Layout;

namespace JidokaUi.Tests.Notifications;

/// <summary>The part of the layout that shows this tab the notifications of the factory watch.</summary>
public sealed class BrowserNotificationsTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private readonly TwoProjects projects = new();
    private readonly TempDirectory home = new();
    private readonly FactoryWatch watch;

    public BrowserNotificationsTests()
    {
        projects.RegisterOn(Services);
        watch = new FactoryWatch(
            new FactoryReader(projects.Catalog, projects.Backlogs),
            projects.Catalog,
            projects.Backlogs,
            projects.Watchers,
            new Heartbeats(new JidokaHome(home.Path)),
            projects.Clock);
        Services.AddSingleton(watch);
        projects.Bd.PrintsIn(projects.First.Value, ListCommand, "[]").PrintsIn(projects.Second.Value, ListCommand, "[]");
    }

    [Fact]
    public void OffersTheAskWhileTheBrowserHasNotBeenAsked()
    {
        JSInterop.Setup<string>(NotificationCall.Name(NotificationCall.Permission)).SetResult("default");

        var layout = Render<BrowserNotifications>();

        layout.WaitForAssertion(() => Assert.Equal(
            "Turn on browser notifications",
            layout.Find(".notifications-ask button").TextContent.Trim()));
    }

    [Fact]
    public void AsksTheBrowserForPermissionOnAPressAndDropsTheAskOnceItGranted()
    {
        JSInterop.Setup<string>(NotificationCall.Name(NotificationCall.Permission)).SetResult("default");
        JSInterop.Setup<string>(NotificationCall.Name(NotificationCall.Request)).SetResult("granted");
        var layout = Render<BrowserNotifications>();
        layout.WaitForElement(".notifications-ask button").Click();

        layout.WaitForAssertion(() => Assert.Empty(layout.FindAll(".notifications-ask")));
        JSInterop.VerifyInvoke(NotificationCall.Name(NotificationCall.Request), calledTimes: 1);
    }

    [Theory]
    [InlineData("granted")]
    [InlineData("denied")]
    [InlineData("unsupported")]
    public void OffersNoAskOnceTheBrowserAnswered(string permission)
    {
        JSInterop.Setup<string>(NotificationCall.Name(NotificationCall.Permission)).SetResult(permission);

        var layout = Render<BrowserNotifications>();

        layout.WaitForAssertion(() => JSInterop.VerifyInvoke(NotificationCall.Name(NotificationCall.Permission)));
        Assert.Empty(layout.FindAll(".notifications-ask"));
    }

    [Fact]
    public async Task ShowsTheBrowserEachNotificationThatTheWatchRaises()
    {
        JSInterop.Setup<string>(NotificationCall.Name(NotificationCall.Permission)).SetResult("granted");
        JSInterop.SetupVoid(NotificationCall.Name(NotificationCall.Show), _ => true);
        Render<BrowserNotifications>();
        await watch.CheckAsync();

        projects.Bd.PrintsIn(
            projects.First.Value,
            ListCommand,
            """
            [
              {"id": "a", "title": "The parser", "issue_type": "epic", "status": "open", "labels": ["factory"],
               "metadata": {"notification": {"acceptance-gate:a":
                 {"fingerprint": "g1", "title": "Ready for acceptance: The parser", "text": "Merge it or drop it, or send it back with /jidoka:accept."}}}}
            ]
            """);
        projects.Backlogs.InvalidateFromWatch(projects.First);
        await watch.CheckAsync();

        var shown = Assert.Single(JSInterop.Invocations, call => call.Identifier == NotificationCall.Name(NotificationCall.Show));
        Assert.Equal("Ready for acceptance: The parser", shown.Arguments[1]);
        Assert.Equal($"bead/a?project={Uri.EscapeDataString(projects.First.Value)}", shown.Arguments[3]);
    }

    protected override void Dispose(bool disposing)
    {
        watch.Dispose();
        projects.Dispose();
        home.Dispose();
        base.Dispose(disposing);
    }
}
