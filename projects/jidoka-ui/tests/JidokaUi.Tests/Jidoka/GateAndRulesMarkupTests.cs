using Bunit;
using Microsoft.Extensions.DependencyInjection;
using JidokaUi.Core.Boards;
using DetailPage = JidokaUi.Web.Components.Pages.Detail;
using JidokaUi.Tests.Boards;

namespace JidokaUi.Tests.Jidoka;

/// <summary>
/// The gate buttons and the rules box on the detail page of an epic, over a hand-written process for
/// jidoka's scripts: which command line each press becomes, what the page says of the script's
/// answer, and that the page writes none of jidoka's keys through bd.
/// </summary>
public sealed class GateAndRulesMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string TheEpicAtTheGate =
        """
        {"id": "b", "title": "The site", "issue_type": "epic", "status": "in_progress",
         "labels": ["factory", "human"], "metadata": {"gate.state": "waiting"}}
        """;

    private const string TheRunningEpic =
        """{"id": "b", "title": "The site", "issue_type": "epic", "status": "in_progress", "labels": ["factory"]}""";

    private const string TheChoices =
        """
        {"epic": "b", "settings": [
          {"name": "lap_test_scope", "choices": ["targeted", "full"], "value": "targeted"},
          {"name": "lap_limit", "choices": [1, 2], "value": null},
          {"name": "commits_on_main", "choices": ["one", "per_task"], "value": null}]}
        """;

    private const string TheItems =
        """
        {"epic": "b",
         "assumptions": [{"number": 1, "bead": "b", "title": "The site", "text": "Dates are UTC"},
                         {"number": 2, "bead": "b-2", "title": "Add two", "text": "Rounds half up"}],
         "removed": [{"test": "AddsTwo", "file": "MathTests.cs", "covered_by": "AddsThree"}],
         "holdouts": [{"number": 1, "app": "shop", "scenario": "Pay 5.00 by card", "promoted": false},
                      {"number": 2, "app": "shop", "scenario": "Pay 5.00 in cash", "promoted": true}],
         "outside": [{"bead": "b-9", "title": "Split the module", "found_in": "b-2"},
                     {"bead": "b-8", "title": "Add a test", "found_in": "b"}]}
        """;

    private const string TheRulesLine =
        """[{"text": "Factory rules: lap_limit set to 1.", "author": "jeff", "created_at": "2026-09-07T10:00:00Z"}]""";

    private readonly TwoProjects projects = new();

    [Fact]
    public void DrawsTheGateButtonsForAnEpicThatWaitsAtTheGate()
    {
        var page = TheDetailPageOf(TheEpicAtTheGate);

        Assert.Equal(["Merge", "Drop"], page.FindAll(".gate-box button").Select(press => press.TextContent));
    }

    [Fact]
    public void DrawsNoGateButtonsForAnEpicThatTheFactoryStillRuns()
    {
        var page = TheDetailPageOf(TheRunningEpic);

        Assert.Empty(page.FindAll(".gate-box"));
    }

    [Fact]
    public void TakesNoMergePressUntilTheCommitMessageHasWords()
    {
        var page = TheDetailPageOf(TheEpicAtTheGate);
        Assert.True(page.Find(".gate-merge").HasAttribute("disabled"));

        page.Find("#gate-message").Input("   ");
        Assert.True(page.Find(".gate-merge").HasAttribute("disabled"));

        page.Find("#gate-message").Input("Add the site");
        Assert.False(page.Find(".gate-merge").HasAttribute("disabled"));
    }

    [Fact]
    public void RunsTheGateScriptWithTheTypedMessageWhenMergeIsPressedAndNamesTheCommit()
    {
        projects.Jidoka.Prints("gate.py merge b --message=Add the site", "4f2a9c1");
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.Find("#gate-message").Input("Add the site");
        page.Find(".gate-merge").Click();

        page.WaitForAssertion(() =>
            Assert.Contains("4f2a9c1", page.Find(".gate-box .bead-write-message").TextContent, StringComparison.Ordinal));
        Assert.Equal(["gate.py merge b --message=Add the site"], TheGateRuns());
        AssertThePageWroteNoKeyThroughBd();
    }

    [Fact]
    public void AsksBeforeItRunsTheDropScriptAndRunsNothingWhenThePersonKeepsTheEpic()
    {
        projects.Jidoka.Prints("gate.py drop b", "b is dropped and closed.");
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.Find(".gate-drop").Click();
        Assert.Empty(TheGateRuns());
        page.Find(".gate-drop-cancel").Click();
        Assert.Empty(TheGateRuns());
        Assert.Single(page.FindAll(".gate-drop"));

        page.Find(".gate-drop").Click();
        page.Find(".gate-drop-confirm").Click();

        page.WaitForAssertion(() => Assert.Equal(["gate.py drop b"], TheGateRuns()));
        AssertThePageWroteNoKeyThroughBd();
    }

    [Fact]
    public void SaysWhatTheGateScriptSaidWhenItRefusesTheDecision()
    {
        projects.Jidoka.Fails("gate.py merge b --message=Add", "gate: the full suite failed");
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.Find("#gate-message").Input("Add");
        page.Find(".gate-merge").Click();

        page.WaitForAssertion(() =>
            Assert.Contains("the full suite failed", page.Find(".gate-box .bead-write-message").TextContent, StringComparison.Ordinal));
    }

    [Fact]
    public void DrawsAPickerForEachSettingThatTheRulesScriptListsWithTheChoicesItGives()
    {
        projects.Jidoka.Prints("rules.py choices b", TheChoices);
        var page = TheDetailPageOf(TheRunningEpic);

        page.WaitForAssertion(() => Assert.Equal(3, page.FindAll(".rules-pick").Count));
        Assert.Equal(["targeted", "full"], OptionsOf(page, "lap_test_scope"));
        Assert.Equal(["not set", "1", "2"], OptionsOf(page, "lap_limit"));
        Assert.Equal("targeted", page.Find("#rule-lap_test_scope").GetAttribute("value"));
    }

    [Fact]
    public void TakesNoSavePressUntilAPickDiffersFromTheValueTheEpicHolds()
    {
        projects.Jidoka.Prints("rules.py choices b", TheChoices);
        var page = TheDetailPageOf(TheRunningEpic);
        page.WaitForAssertion(() => Assert.Equal(3, page.FindAll(".rules-pick").Count));
        Assert.True(page.Find(".rules-save").HasAttribute("disabled"));

        page.Find("#rule-lap_test_scope").Change("full");

        Assert.False(page.Find(".rules-save").HasAttribute("disabled"));
    }

    [Fact]
    public void RunsTheRulesScriptWithTheChangedSettingAndShowsItsCommentOnTheEpic()
    {
        projects.Jidoka
            .Prints("rules.py choices b", TheChoices)
            .Prints("rules.py set b lap_limit=1", "{}")
            .After("rules.py set b lap_limit=1", () =>
                projects.Bd.PrintsIn(projects.Second.Value, "comments b --json", TheRulesLine));
        var page = TheDetailPageOf(TheRunningEpic);
        page.WaitForAssertion(() => Assert.Equal(3, page.FindAll(".rules-pick").Count));

        page.Find("#rule-lap_limit").Change("1");
        page.Find(".rules-save").Click();

        page.WaitForAssertion(() =>
            Assert.Equal(
                ["Factory rules: lap_limit set to 1."],
                page.FindAll(".bead-comment-text").Select(text => text.TextContent.Trim())));
        Assert.Contains("rules.py set b lap_limit=1", projects.Jidoka.Invocations);
        AssertThePageWroteNoKeyThroughBd();
    }

    [Fact]
    public void SendsEverySettingThatDiffersInOneRunOfTheRulesScript()
    {
        projects.Jidoka
            .Prints("rules.py choices b", TheChoices)
            .Prints("rules.py set b lap_test_scope=\"full\" commits_on_main=\"per_task\"", "{}");
        var page = TheDetailPageOf(TheRunningEpic);
        page.WaitForAssertion(() => Assert.Equal(3, page.FindAll(".rules-pick").Count));

        page.Find("#rule-lap_test_scope").Change("full");
        page.Find("#rule-commits_on_main").Change("per_task");
        page.Find(".rules-save").Click();

        page.WaitForAssertion(() =>
            Assert.Contains("rules.py set b lap_test_scope=\"full\" commits_on_main=\"per_task\"", projects.Jidoka.Invocations));
    }

    [Fact]
    public void SaysWhyTheRulesScriptRefusedAValueAndKeepsThePicks()
    {
        projects.Jidoka
            .Prints("rules.py choices b", TheChoices)
            .Fails("rules.py set b lap_limit=2", "rules: lap_limit must be below the repo's 2");
        var page = TheDetailPageOf(TheRunningEpic);
        page.WaitForAssertion(() => Assert.Equal(3, page.FindAll(".rules-pick").Count));

        page.Find("#rule-lap_limit").Change("2");
        page.Find(".rules-save").Click();

        page.WaitForAssertion(() =>
            Assert.Contains("must be below the repo's 2", page.Find(".rules-box .bead-write-message").TextContent, StringComparison.Ordinal));
        Assert.False(page.Find(".rules-save").HasAttribute("disabled"));
    }

    [Fact]
    public void SaysWhyThePickersAreMissingWhenTheRulesScriptGivesNoSettings()
    {
        projects.Jidoka.Fails("rules.py choices b", "rules: the factory rules of b cannot be read");
        var page = TheDetailPageOf(TheRunningEpic);

        page.WaitForAssertion(() =>
            Assert.Contains("cannot be read", page.Find(".rules-unread").TextContent, StringComparison.Ordinal));
        Assert.Empty(page.FindAll(".rules-pick"));
    }

    [Fact]
    public void DrawsNoRulesBoxForATaskAndAsksTheRulesScriptNothing()
    {
        var page = TheDetailPageOf("""{"id": "b", "title": "A task", "issue_type": "task", "status": "open"}""");

        Assert.Empty(page.FindAll(".rules-box"));
        Assert.Empty(projects.Jidoka.Invocations);
    }

    [Fact]
    public void DrawsNoRulesBoxForAnOpenEpicWithoutTheFactoryLabel()
    {
        var page = TheDetailPageOf(TheRunningEpic.Replace("\"factory\"", "\"web\"", StringComparison.Ordinal));

        Assert.Empty(page.FindAll(".rules-box"));
        Assert.Empty(projects.Jidoka.Invocations);
    }

    [Fact]
    public void DrawsNoRulesBoxForAClosedEpic()
    {
        var page = TheDetailPageOf(TheRunningEpic.Replace("in_progress", "closed", StringComparison.Ordinal));

        Assert.Empty(page.FindAll(".rules-box"));
        Assert.Empty(projects.Jidoka.Invocations);
    }

    [Fact]
    public void DrawsEachAssumptionTheGateScriptNumbersWithAButtonToMarkItWrong()
    {
        projects.Jidoka.Prints("gate.py items b", TheItems);
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.WaitForAssertion(() => Assert.Equal(2, page.FindAll(".gate-assumption").Count));
        var rows = page.FindAll(".gate-assumption").Select(row => row.TextContent).ToList();
        Assert.Contains("1", rows[0], StringComparison.Ordinal);
        Assert.Contains("Dates are UTC", rows[0], StringComparison.Ordinal);
        Assert.Contains("2", rows[1], StringComparison.Ordinal);
        Assert.Contains("Rounds half up", rows[1], StringComparison.Ordinal);
        Assert.Equal(2, page.FindAll(".gate-wrong").Count);
    }

    [Fact]
    public void DrawsEachTestTheCleanupRemovedWithItsFileAndWhatCoversItAndAButtonToRestoreIt()
    {
        projects.Jidoka.Prints("gate.py items b", TheItems);
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.WaitForAssertion(() => Assert.Single(page.FindAll(".gate-removed-test")));
        var row = page.Find(".gate-removed-test").TextContent;
        Assert.Contains("AddsTwo", row, StringComparison.Ordinal);
        Assert.Contains("MathTests.cs", row, StringComparison.Ordinal);
        Assert.Contains("AddsThree", row, StringComparison.Ordinal);
        Assert.Single(page.FindAll(".gate-restore"));
    }

    [Fact]
    public void DrawsEachBeadFoundOutsideTheEpicWithKeepAndCloseButtons()
    {
        projects.Jidoka.Prints("gate.py items b", TheItems);
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.WaitForAssertion(() => Assert.Equal(2, page.FindAll(".gate-finding").Count));
        Assert.Contains("Split the module", page.FindAll(".gate-finding")[0].TextContent, StringComparison.Ordinal);
        Assert.Equal(["Keep", "Close"], page.FindAll(".gate-finding")[0].QuerySelectorAll("button").Select(press => press.TextContent));
        Assert.Equal(2, page.FindAll(".gate-keep").Count);
        Assert.Equal(2, page.FindAll(".gate-close").Count);
    }

    [Fact]
    public void DrawsEachHoldoutWithItsAppAndScenarioAndAPromoteButtonUntilItIsPromoted()
    {
        projects.Jidoka.Prints("gate.py items b", TheItems);
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.WaitForAssertion(() => Assert.Equal(2, page.FindAll(".gate-holdout").Count));
        var rows = page.FindAll(".gate-holdout");
        Assert.Contains("shop", rows[0].TextContent, StringComparison.Ordinal);
        Assert.Contains("Pay 5.00 by card", rows[0].TextContent, StringComparison.Ordinal);
        Assert.Equal(["Promote"], rows[0].QuerySelectorAll("button").Select(press => press.TextContent));
        Assert.Contains("Pay 5.00 in cash", rows[1].TextContent, StringComparison.Ordinal);
        Assert.Empty(rows[1].QuerySelectorAll("button"));
        Assert.Contains("Promoted", rows[1].TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void RunsPromoteWithTheNumberOfTheHoldoutThatWasPressed()
    {
        projects.Jidoka
            .Prints("gate.py items b", TheItems)
            .Prints("gate.py promote b 1", "Holdout 1 of b is promoted.");
        var page = TheDetailPageOf(TheEpicAtTheGate);
        page.WaitForAssertion(() => Assert.Single(page.FindAll(".gate-promote")));

        page.Find(".gate-promote").Click();

        page.WaitForAssertion(() => Assert.Equal(["gate.py promote b 1"], TheGateRuns()));
        page.WaitForAssertion(() =>
            Assert.Contains("is promoted", page.Find(".gate-items-box .bead-write-message").TextContent, StringComparison.Ordinal));
        AssertThePageWroteNoKeyThroughBd();
    }

    [Fact]
    public void DrawsNothingForASectionTheGateScriptListsNoItemOf()
    {
        projects.Jidoka.Prints(
            "gate.py items b",
            """{"epic": "b", "assumptions": [], "removed": [], "holdouts": [], "outside": [{"bead": "b-9", "title": "Split", "found_in": "b"}]}""");
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.WaitForAssertion(() => Assert.Single(page.FindAll(".gate-finding")));
        Assert.Empty(page.FindAll(".gate-assumption"));
        Assert.Empty(page.FindAll(".gate-removed-test"));
    }

    [Fact]
    public void AsksTheGateScriptForNoItemsOfAnEpicThatTheFactoryStillRuns()
    {
        var page = TheDetailPageOf(TheRunningEpic);

        page.WaitForAssertion(() => Assert.Single(page.FindAll(".rules-box")));
        Assert.Empty(page.FindAll(".gate-items-box"));
        Assert.DoesNotContain(projects.Jidoka.Invocations, line => line.StartsWith("gate.py", StringComparison.Ordinal));
    }

    [Fact]
    public void SaysWhyTheItemsAreMissingWhenTheGateScriptGivesNone()
    {
        projects.Jidoka.Fails("gate.py items b", "gate: b does not wait at the acceptance gate");
        var page = TheDetailPageOf(TheEpicAtTheGate);

        page.WaitForAssertion(() =>
            Assert.Contains("does not wait", page.Find(".gate-items-unread").TextContent, StringComparison.Ordinal));
        Assert.Empty(page.FindAll(".gate-wrong"));
    }

    [Fact]
    public void AsksForTheReasonBeforeItRunsWrongAndRunsItWithTheNumberAndTheReason()
    {
        projects.Jidoka
            .Prints("gate.py items b", TheItems)
            .Prints("gate.py wrong b 2 --why=It is a guess", "Assumption 2 of b is marked wrong on b-2.");
        var page = TheDetailPageOf(TheEpicAtTheGate);
        page.WaitForAssertion(() => Assert.Equal(2, page.FindAll(".gate-wrong").Count));

        page.FindAll(".gate-wrong")[1].Click();
        Assert.Empty(TheGateRuns());
        Assert.True(page.Find(".gate-wrong-send").HasAttribute("disabled"));
        page.Find(".gate-wrong-why").Input("   ");
        Assert.True(page.Find(".gate-wrong-send").HasAttribute("disabled"));
        page.Find(".gate-wrong-why").Input("It is a guess");
        page.Find(".gate-wrong-send").Click();

        page.WaitForAssertion(() => Assert.Equal(["gate.py wrong b 2 --why=It is a guess"], TheGateRuns()));
        page.WaitForAssertion(() =>
            Assert.Contains("marked wrong on b-2", page.Find(".gate-items-box .bead-write-message").TextContent, StringComparison.Ordinal));
        AssertThePageWroteNoKeyThroughBd();
    }

    [Fact]
    public void RunsRestoreWithTheTestAndItsFile()
    {
        projects.Jidoka
            .Prints("gate.py items b", TheItems)
            .Prints("gate.py restore b AddsTwo --file=MathTests.cs", "abc1234");
        var page = TheDetailPageOf(TheEpicAtTheGate);
        page.WaitForAssertion(() => Assert.Single(page.FindAll(".gate-restore")));

        page.Find(".gate-restore").Click();

        page.WaitForAssertion(() => Assert.Equal(["gate.py restore b AddsTwo --file=MathTests.cs"], TheGateRuns()));
        AssertThePageWroteNoKeyThroughBd();
    }

    [Fact]
    public void RunsKeepAndCloseWithTheBeadOfTheRowThatWasPressed()
    {
        projects.Jidoka
            .Prints("gate.py items b", TheItems)
            .Prints("gate.py keep-finding b b-9", "b-9 stays open.")
            .Prints("gate.py close-finding b b-8", "b-8 is closed.");
        var page = TheDetailPageOf(TheEpicAtTheGate);
        page.WaitForAssertion(() => Assert.Equal(2, page.FindAll(".gate-finding").Count));

        page.FindAll(".gate-keep")[0].Click();
        page.WaitForAssertion(() => Assert.Single(TheGateRuns()));
        page.FindAll(".gate-close")[1].Click();

        page.WaitForAssertion(() =>
            Assert.Equal(["gate.py keep-finding b b-9", "gate.py close-finding b b-8"], TheGateRuns()));
    }

    [Fact]
    public void SaysWhatTheGateScriptSaidWhenItRefusesASmallDecision()
    {
        projects.Jidoka
            .Prints("gate.py items b", TheItems)
            .Fails("gate.py close-finding b b-9", "gate: b-9 is no open bead found outside b");
        var page = TheDetailPageOf(TheEpicAtTheGate);
        page.WaitForAssertion(() => Assert.Equal(2, page.FindAll(".gate-finding").Count));

        page.FindAll(".gate-close")[0].Click();

        page.WaitForAssertion(() =>
            Assert.Contains("no open bead found outside", page.Find(".gate-items-box .bead-write-message").TextContent, StringComparison.Ordinal));
    }

    [Fact]
    public void ReadsTheItemsAgainAfterADecisionSoAClosedFindingLeavesTheList()
    {
        projects.Jidoka
            .Prints("gate.py items b", TheItems)
            .Prints("gate.py close-finding b b-9", "b-9 is closed.")
            .After("gate.py close-finding b b-9", () =>
                projects.Jidoka.Prints(
                    "gate.py items b",
                    """{"epic": "b", "assumptions": [], "removed": [], "holdouts": [], "outside": [{"bead": "b-8", "title": "Add a test", "found_in": "b-2"}]}"""));
        var page = TheDetailPageOf(TheEpicAtTheGate);
        page.WaitForAssertion(() => Assert.Equal(2, page.FindAll(".gate-finding").Count));

        page.FindAll(".gate-close")[0].Click();

        page.WaitForAssertion(() => Assert.Single(page.FindAll(".gate-finding")));
        Assert.Contains("Add a test", page.Find(".gate-finding").TextContent, StringComparison.Ordinal);
    }

    private List<string> TheGateRuns() =>
        [.. projects.Jidoka.Invocations.Where(line =>
            line.StartsWith("gate.py ", StringComparison.Ordinal)
            && !line.StartsWith("gate.py items ", StringComparison.Ordinal))];

    private static IEnumerable<string> OptionsOf(IRenderedComponent<DetailPage> page, string setting) =>
        page.FindAll($"#rule-{setting} option").Select(option => option.TextContent);

    private void AssertThePageWroteNoKeyThroughBd() =>
        Assert.DoesNotContain(
            projects.Bd.Invocations,
            line => !line.EndsWith("--help", StringComparison.Ordinal)
                && (line.Contains("--set-metadata", StringComparison.Ordinal)
                    || line.StartsWith("update ", StringComparison.Ordinal)));

    private IRenderedComponent<DetailPage> TheDetailPageOf(string bead)
    {
        projects.Bd
            .DeclaresEveryWrite()
            .PrintsIn(projects.Second.Value, "show b --json", $"[{bead}]")
            .PrintsIn(projects.Second.Value, "comments b --json", "[]")
            .PrintsIn(projects.Second.Value, ListCommand, $"[{bead}]")
            .PrintsIn(projects.First.Value, ListCommand, "[]");
        projects.RegisterOn(Services);
        Services.AddSingleton(new BeadDetailReader(projects.Adapter, new BacklogReader(projects.Adapter)));
        Services.GetRequiredService<Microsoft.AspNetCore.Components.NavigationManager>()
            .NavigateTo($"bead/b?project={Uri.EscapeDataString(projects.Second.Value)}");

        return Render<DetailPage>(parameters => parameters.Add(page => page.Id, "b"));
    }
}
