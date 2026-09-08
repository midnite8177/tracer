using Bunit;
using TracerUi.Web.Components.Layout;

namespace TracerUi.Tests.Look;

/// <summary>
/// The script that carries the theme onto the document. The words it writes are written out here,
/// because the stylesheets state the same attribute and the same two names in selectors that no
/// compiler follows: a rename that only the Theme type knows about is a dark page that stays light.
/// </summary>
public sealed class ThemeScriptTests : BunitContext
{
    [Fact]
    public void WritesTheThemeOntoTheAttributeThatTheStylesheetsSelectOn()
    {
        Assert.Contains("\"data-bs-theme\"", TheScript(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("light")]
    [InlineData("dark")]
    public void CarriesTheNameOfEachThemeThatTheStylesheetsSelectOn(string name)
    {
        Assert.Contains($"\"{name}\"", TheScript(), StringComparison.Ordinal);
    }

    private string TheScript() => Render<ThemeScript>().Markup;
}
