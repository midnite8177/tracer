using Bunit;
using TracerUi.Core.Look;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Look;

/// <summary>
/// The script that answers the ask of a row for a new tab. Nothing but this script answers the
/// call, so a script that stopped defining the name would leave every ask unanswered in the
/// browser alone.
/// </summary>
public sealed class NewTabScriptTests : BunitContext
{
    [Fact]
    public void DefinesTheCallThatARowAsksForANewTabWith()
    {
        var script = Render<NewTabScript>().Markup;

        Assert.Contains($"window[\"{NewTabCall.Holder}\"]", script, StringComparison.Ordinal);
        Assert.Contains($"\"{NewTabCall.Open}\": function", script, StringComparison.Ordinal);
    }
}
