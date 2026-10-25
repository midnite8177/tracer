using Bunit;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Look;
using JidokaUi.Web.Components.Layout;

namespace JidokaUi.Tests.Look;

public sealed class CopyButtonTests : BunitContext
{
    [Fact]
    public void ShowsTheReasonInWordsWhenThePressReachesNoClipboard()
    {
        var button = PressTheButtonFor("jidoka-1", "no-clipboard");

        Assert.Equal(
            "The browser needs a secure connection.",
            button.Find(".copy-reason").TextContent.Trim());
    }

    [Fact]
    public void ShowsTheRefusalInWordsWhenTheBrowserWouldNotWriteToItsClipboard()
    {
        var button = PressTheButtonFor("jidoka-1", "refused");

        Assert.Equal(
            "The browser would not write to the clipboard.",
            button.Find(".copy-reason").TextContent.Trim());
    }

    [Fact]
    public void KeepsTheReasonOutOfTheRegionThatOnlyAScreenReaderReads()
    {
        var button = PressTheButtonFor("jidoka-1", "no-clipboard");

        Assert.Empty(button.FindAll(".copy-announcement .copy-reason"));
        Assert.Equal("true", button.Find(".copy-reason").GetAttribute("aria-hidden"));
    }

    [Fact]
    public void ShowsNoReasonInWordsWhenTheClipboardTookTheText()
    {
        var button = PressTheButtonFor("jidoka-1", "took");

        Assert.Empty(button.FindAll(".copy-reason"));
    }

    [Fact]
    public void TakesTheReasonOffTheButtonOfATextThatNoPersonPressedItFor()
    {
        var feedback = new CopyFeedback();
        feedback.FoundNoClipboard("jidoka-1");
        Services.AddSingleton(feedback);

        var button = Render<CopyButton>(p => p.Add(c => c.Text, "jidoka-2"));

        Assert.Empty(button.FindAll(".copy-reason"));
    }

    private IRenderedComponent<CopyButton> PressTheButtonFor(string text, string outcome)
    {
        JSInterop.Setup<string>("jidokaClipboard.write", text).SetResult(outcome);
        Services.AddSingleton(new CopyFeedback());
        var button = Render<CopyButton>(p => p.Add(c => c.Text, text));

        button.Find("button").Click();

        return button;
    }
}
