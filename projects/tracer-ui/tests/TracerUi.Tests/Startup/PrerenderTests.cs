using TracerUi.Core.Beads;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Startup;

/// <summary>What the app puts in an HTTP response, before the browser holds a circuit.</summary>
public sealed class PrerenderTests
{
    [Fact]
    public async Task RunsNoBdCommandWhileItAnswersTheNeedsYouRequest()
    {
        using var app = new AnAppOverHttp();
        using var browser = app.CreateClient();

        using var response = await browser.GetAsync("/needs-you");

        response.EnsureSuccessStatusCode();
        Assert.Empty(app.Bd.Invocations);
    }

    [Fact]
    public async Task RunsNoBdCommandWhileItAnswersTheRequestForABeadOfANamedProject()
    {
        using var app = new AnAppOverHttp();
        using var browser = app.CreateClient();

        using var response = await browser.GetAsync(
            BeadPageAddress.Of(new BeadAddress(app.Projects[0], "x-1")));

        response.EnsureSuccessStatusCode();
        Assert.Empty(app.Bd.Invocations);
    }

    [Fact]
    public async Task PutsNoBoardPageInTheBodyOfTheBoardResponse()
    {
        using var app = new AnAppOverHttp();
        using var browser = app.CreateClient();

        var body = await browser.GetStringAsync("/board");

        Assert.DoesNotContain(NoActiveProject.Ask, body, StringComparison.Ordinal);
    }
}
