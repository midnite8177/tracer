using TracerUi.Core.Look;

namespace TracerUi.Tests.Look;

public sealed class ThemeTests
{
    [Fact]
    public void ReadsTheStoredWordOfEachTheme()
    {
        Assert.True(Theme.TryParse("light", out var light));
        Assert.True(Theme.TryParse("dark", out var dark));

        Assert.Equal(Theme.Light, light);
        Assert.Equal(Theme.Dark, dark);
    }

    [Theory]
    [InlineData("Dark")]
    [InlineData("midnight")]
    [InlineData("")]
    [InlineData(null)]
    public void RefusesAWordThatNeitherThemeCarries(string? stored)
    {
        Assert.False(Theme.TryParse(stored, out var theme));
        Assert.Null(theme);
    }

    [Fact]
    public void GivesTheOtherThemeOnAToggle()
    {
        Assert.Equal(Theme.Dark, Theme.Light.Other);
        Assert.Equal(Theme.Light, Theme.Dark.Other);
    }

    [Fact]
    public void ReadsBackTheWordThatItGivesTheBrowserToStore()
    {
        Assert.True(Theme.TryParse(Theme.Light.Name, out var light));
        Assert.True(Theme.TryParse(Theme.Dark.Name, out var dark));

        Assert.Equal(Theme.Light, light);
        Assert.Equal(Theme.Dark, dark);
        Assert.NotEqual(Theme.Light.Name, Theme.Dark.Name);
    }

    [Fact]
    public void ReadsTheThemeThatTheDocumentCarries()
    {
        Assert.Equal(Theme.Light, Theme.FromDocument("light"));
        Assert.Equal(Theme.Dark, Theme.FromDocument("dark"));
    }

    [Theory]
    [InlineData("Dark")]
    [InlineData("midnight")]
    [InlineData("")]
    [InlineData(null)]
    public void ReadsADocumentWithNoThemeAsTheLightOne(string? attribute)
    {
        Assert.Equal(Theme.Light, Theme.FromDocument(attribute));
    }

    [Fact]
    public void ComesBackToItselfAfterTwoToggles()
    {
        Assert.Equal(Theme.Light, Theme.Light.Other.Other);
    }
}
