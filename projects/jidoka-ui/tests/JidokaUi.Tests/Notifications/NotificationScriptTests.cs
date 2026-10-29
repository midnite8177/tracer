using Bunit;
using JidokaUi.Core.Notifications;
using JidokaUi.Web.Components.Layout;

namespace JidokaUi.Tests.Notifications;

/// <summary>
/// The script that answers the calls for a notification. Nothing but this script answers them, so
/// a script that stopped defining a name would leave the call unanswered in the browser alone.
/// </summary>
public sealed class NotificationScriptTests : BunitContext
{
    [Theory]
    [InlineData(NotificationCall.Permission)]
    [InlineData(NotificationCall.Request)]
    [InlineData(NotificationCall.Show)]
    public void DefinesEachCallThatTheAppMakes(string call)
    {
        var script = Render<NotificationScript>().Markup;

        Assert.Contains($"window[\"{NotificationCall.Holder}\"]", script, StringComparison.Ordinal);
        Assert.Matches($"\"{call}\": (async )?function", script);
    }
}
