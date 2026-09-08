using AngleSharp.Dom;
using Bunit;
using Microsoft.AspNetCore.Components;
using Bunit.Web.AngleSharp;
using Microsoft.Extensions.DependencyInjection;
using TracerUi.Core.Boards;
using TracerUi.Core.Projects;
using DetailPage = TracerUi.Web.Components.Pages.Detail;

namespace TracerUi.Tests.Boards;

/// <summary>The detail page as a browser draws it, and the project that its own address names.</summary>
public sealed class DetailMarkupTests : BunitContext
{
    private const string ListCommand = "list --all --limit 0 --json";

    private const string TheBeadOfTheSecondProject =
        """[{"id": "b-7", "title": "Pick a hosting plan", "status": "open"}]""";

    private const string TheTitleOfThatBead = "Pick a hosting plan";

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
    public void SaysThatTheProjectOfItsAddressLeftTheRegistryAndReadsTheBeadOfNoOtherProject()
    {
        projects.Forget(projects.Second);

        var page = ThePageAt(TheAddressOfTheBead, theActiveProject: projects.First);

        Assert.Contains("second", page.Find("p.bead-message").TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain(TheTitleOfThatBead, page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void DrawsTheBeadWhenTheBrowserGivesItsProjectBackToATabThatHeldNone()
    {
        var page = ThePageAt("bead/b-7");

        projects.Selection.Restore(projects.Second.Value);

        page.WaitForAssertion(() =>
            Assert.Contains(TheTitleOfThatBead, page.Find("h1").TextContent, StringComparison.Ordinal));
        Assert.EndsWith("bead/b-7", TheAddress(), StringComparison.Ordinal);
    }

    [Fact]
    public void LeavesForTheBoardWhenAPersonSwitchesTheProject()
    {
        var page = ThePageAt(TheAddressOfTheBead);

        projects.Selection.Select(projects.First);

        page.WaitForAssertion(() => Assert.EndsWith("board", TheAddress(), StringComparison.Ordinal));
    }

    // A bead with every fact that the fact strip states, so that one page shows every box. The
    // show of the bead and the backlog beside it name the same record, thus neither drifts from
    // the other.
    private const string TheRecordOfThatBead =
        """
        {"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2,
         "status": "open", "labels": ["human"], "parent": "b-1",
         "description": "Two plans remain.", "acceptance_criteria": "One plan wins.",
         "notes": "The vendor answers slowly.",
         "dependencies": [{"id": "b-9", "dependency_type": "blocks"}]}
        """;

    // The bead that blocks it, so that the Blocked by list holds one bead. It carries the second
    // label of the project, thus the labels picker offers a label that the bead of every fact lacks.
    private const string TheRecordOfItsBlocker =
        """
        {"id": "b-9", "title": "Choose a registrar", "issue_type": "task", "status": "open",
         "labels": ["docs"]}
        """;

    // The bead that waits for it, so that the Blocks list holds one bead.
    private const string TheRecordOfItsDependent =
        """
        {"id": "b-10", "title": "Launch the site", "issue_type": "feature", "status": "open",
         "dependencies": [{"id": "b-7", "dependency_type": "blocks"}]}
        """;

    // A bead that names nothing beside its title and its description: no blocker, no dependent, no
    // held bead, no acceptance criteria and no notes. It is the leaf bead, which is the common one.
    private const string TheBareRecord =
        """
        {"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2,
         "status": "open", "description": "Two plans remain."}
        """;

    private const string TheBareBead = $"[{TheBareRecord}]";

    // The backlog that holds the bare bead, and one epic that a picker could offer.
    private const string TheBacklogOfTheBareBead = $"[{TheRecordOfASecondEpic}, {TheBareRecord}]";

    // The bare bead as bd shows it when one bead blocks it and nothing else names it.
    private const string TheBareBeadWithABlocker =
        """
        [{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2,
          "status": "open", "description": "Two plans remain.",
          "dependencies": [{"id": "b-9", "dependency_type": "blocks"}]}]
        """;

    private const string TheBareBeadWithAcceptanceCriteria =
        """
        [{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2,
          "status": "open", "description": "Two plans remain.",
          "acceptance_criteria": "One plan wins."}]
        """;

    private const string TheBareBeadWithNotes =
        """
        [{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2,
          "status": "open", "description": "Two plans remain.",
          "notes": "The vendor answers slowly."}]
        """;

    // A bead that states no prose at all, so that the description box says it has none.
    private const string TheBeadOfNoProseAtAll =
        """
        [{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2,
          "status": "open"}]
        """;

    private const string TheBacklogOfABeadWithABlocker =
        $"[{TheBareRecord}, {TheRecordOfItsBlocker}]";

    private const string TheBacklogOfABeadWithADependent =
        $"[{TheBareRecord}, {TheRecordOfItsDependent}]";

    private const string TheBacklogOfABeadWithAHeldBead =
        $"[{TheBareRecord}, {TheRecordOfADeeperBead}]";

    // The epic that holds that bead. It states its acceptance criteria and carries notes, so that
    // its page draws every prose box and the order of the boxes is the one a person reads.
    private const string TheRecordOfItsEpic =
        """
        {"id": "b-1", "title": "Ship the site", "issue_type": "epic", "status": "in_progress",
         "acceptance_criteria": "The site answers.", "notes": "The vendor answers slowly."}
        """;

    // A second epic, so that the epic picker offers one that does not hold this bead.
    private const string TheRecordOfASecondEpic =
        """{"id": "b-2", "title": "Choose the vendor", "issue_type": "epic", "status": "open"}""";

    private const string TheBeadWithEveryFact = $"[{TheRecordOfThatBead}]";

    private const string TheClosedBead =
        """
        [{"id": "b-7", "title": "Pick a hosting plan", "issue_type": "task", "priority": 2,
          "status": "closed", "parent": "b-1", "close_reason": "The vendor answered.",
          "description": "Two plans remain."}]
        """;

    private const string TheComments =
        """[{"text": "Read the two plans again.", "author": "claude", "created_at": "2026-09-07T10:00:00Z"}]""";

    private const string TheBacklogOfThatBead =
        $"[{TheRecordOfItsEpic}, {TheRecordOfASecondEpic}, {TheRecordOfThatBead}, "
        + $"{TheRecordOfItsBlocker}, {TheRecordOfItsDependent}]";

    // A closed bead that the same epic holds, so that the held beads box has one of each.
    private const string TheRecordOfAClosedHeldBead =
        """
        {"id": "b-8", "title": "Register the domain name", "issue_type": "chore", "priority": 1,
         "status": "closed", "parent": "b-1"}
        """;

    // A bead that the bead of every fact holds, one level below the epic.
    private const string TheRecordOfADeeperBead =
        """
        {"id": "b-7-1", "title": "Read the two plans", "issue_type": "task", "priority": 2,
         "status": "open", "parent": "b-7"}
        """;

    private const string TheCreateOfTheNewBead =
        "create --title Read the two plans again --type task --parent b-1 --silent";

    private const string TheRecordOfTheNewBead =
        """
        {"id": "b-1.1", "title": "Read the two plans again", "issue_type": "task", "status": "open",
         "parent": "b-1"}
        """;

    private const string TheRecordsOfTheEpic =
        $"{TheRecordOfItsEpic}, {TheRecordOfThatBead}, {TheRecordOfAClosedHeldBead}, {TheRecordOfADeeperBead}";

    private const string TheBacklogOfTheEpic = $"[{TheRecordsOfTheEpic}]";

    [Fact]
    public void DrawsEachOfTheFiveShortFactsOfTheBeadInABoxOfTheFactStrip()
    {
        var page = ThePageOfTheBeadWithEveryFact();

        var facts = page.FindAll(".bead-fact-strip .bead-fact");
        Assert.Equal(
            ["Status", "Priority", "Type", "Labels", "Epic"],
            facts.Select(fact => TheOneIn(".bead-fact-name", fact).TextContent.Trim()));
        Assert.Equal(
            ["needs you", "p2", "task", "human", "Ship the site"],
            facts.Select(fact => TheOneIn(".bead-fact-press", fact).TextContent.Trim()));
        Assert.Contains("bead-status-needs-you", TheOneIn(".bead-fact-value", facts[0]).ClassList);
    }

    [Fact]
    public void SaysTheTitleAndTheQuietIdInTheHeadAndStatesNoFactBesideThem()
    {
        var page = ThePageOfTheBeadWithEveryFact();

        var head = page.Find(".bead-head");
        Assert.Equal("board", TheOneIn("a", head).GetAttribute("href"));
        Assert.Contains(TheTitleOfThatBead, TheOneIn("h1", head).TextContent, StringComparison.Ordinal);
        Assert.Equal("b-7", TheOneIn("code.machine-text-quiet", head).TextContent);
        Assert.NotNull(head.QuerySelector(".copy-button"));
        Assert.DoesNotContain("task", head.TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain("p2", head.TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain("needs you", head.TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain("Ship the site", head.TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void DrawsEveryProseSectionOfTheBeadAsABoxOfItsOwn()
    {
        var page = ThePageOfTheBeadWithEveryFact();

        var boxes = page.FindAll(".bead-prose-column .bead-box");
        Assert.Equal(
            ["Description", "Dependencies", "Acceptance criteria", "Notes", "Comments"],
            boxes.Select(box => TheOneIn("h2", box).TextContent.Trim()));
    }

    [Fact]
    public void DrawsTheHeldBeadsOfAnEpicInABoxBetweenTheDescriptionAndTheDependencies()
    {
        var page = ThePageOfTheEpic();

        var boxes = page.FindAll(".bead-prose-column .bead-box");
        Assert.Equal(
            ["Description", "Held beads", "Dependencies", "Acceptance criteria", "Notes", "Comments"],
            boxes.Select(box => TheOneIn("h2", box).TextContent.Trim()));
    }

    [Fact]
    public void DrawsAHeldBeadAsAStatusDotATitleLinkAndTheTypeAndTheIdAsQuietMachineText()
    {
        var page = ThePageOfTheEpic();

        var row = page.Find(".bead-held .bead-row");
        Assert.Contains("bead-status-needs-you", TheOneIn(".bead-dot", row).ClassList);
        Assert.Equal("needs you", TheOneIn(".visually-hidden", row).TextContent.Trim());
        Assert.Equal("bead/b-7", TheOneIn("a", row).GetAttribute("href"));
        Assert.Equal(TheTitleOfThatBead, TheOneIn("a", row).TextContent.Trim());
        Assert.Equal(
            ["task", "b-7"],
            row.QuerySelectorAll("code.machine-text-quiet").Select(one => one.TextContent.Trim()));
        Assert.NotNull(row.QuerySelector(".copy-button"));
    }

    [Fact]
    public void ListsTheOpenHeldBeadsAndLeavesTheClosedOnesBehindAPress()
    {
        var page = ThePageOfTheEpic();

        Assert.Equal(
            [TheTitleOfThatBead],
            page.FindAll(".bead-held .bead-row-title").Select(row => row.TextContent.Trim()));
        Assert.Equal("Add the closed bead", page.Find(".bead-held-press").TextContent.Trim());
    }

    [Fact]
    public void AddsTheClosedHeldBeadsStruckThroughOnAPress()
    {
        var page = ThePageOfTheEpic();

        page.Find(".bead-held-press").Click();

        var rows = page.FindAll(".bead-held .bead-row");
        Assert.Equal(
            [TheTitleOfThatBead, "Register the domain name"],
            rows.Select(row => TheOneIn(".bead-row-title", row).TextContent.Trim()));
        Assert.DoesNotContain("bead-row-closed", rows[0].ClassList);
        Assert.Contains("bead-row-closed", rows[1].ClassList);
        Assert.Empty(page.FindAll(".bead-held-press"));
    }

    [Fact]
    public void OffersAPressOnTheHeldBeadsBoxThatOpensTheQuickCreateOfABeadInsideThisEpic()
    {
        var page = ThePageOfTheEpicThatTakesACreate();

        page.Find(".bead-held-add").Click();

        Assert.Single(page.FindAll("#held-create-title"));
        Assert.Single(page.FindAll("#held-create-type"));
    }

    [Fact]
    public void OffersEveryTypeButTheEpicInTheQuickCreateOfTheEpicsPage()
    {
        var page = ThePageOfTheEpicThatTakesACreate();

        page.Find(".bead-held-add").Click();

        Assert.Equal(
            AQuickCreate.TheTypesItOffersSpelledOut,
            AQuickCreate.TheTypesItOffers(page, "held-create-type"));
    }

    [Fact]
    public void LabelsTheTitleBoxAndTheTypePickerOfTheQuickCreateOfTheEpicsPage()
    {
        var page = ThePageOfTheEpicThatTakesACreate();

        page.Find(".bead-held-add").Click();

        Assert.Equal("A bead inside this one", AQuickCreate.TheLabelOf(page, "held-create-title"));
        Assert.Equal("Type", AQuickCreate.TheLabelOf(page, "held-create-type"));
    }

    [Fact]
    public void DrawsTheFieldsOfTheQuickCreateOfTheEpicsPageFromTheComponentThatEverySurfaceShares()
    {
        var page = ThePageOfTheEpicThatTakesACreate();

        page.Find(".bead-held-add").Click();

        Assert.NotNull(AQuickCreate.TheFieldsOf(page));
    }

    [Fact]
    public void OffersNoEpicInTheQuickCreateOfTheEpicsPageBecauseTheEpicIsTheBeadOfThePage()
    {
        var page = ThePageOfTheEpicThatTakesACreate();

        page.Find(".bead-held-add").Click();

        Assert.Empty(AQuickCreate.TheFieldsOf(page).FindAll("select.form-select:not(#held-create-type)"));
    }

    [Fact]
    public void MakesTheBeadInsideThisEpicAndListsItWithNoReloadOfThePage()
    {
        var page = ThePageOfTheEpicThatMakesABeadInsideIt();

        page.Find(".bead-held-add").Click();
        page.Find("#held-create-title").Input("Read the two plans again");
        page.Find(".bead-held-create-write").Click();

        Assert.Contains(TheCreateOfTheNewBead, projects.Bd.Invocations);
        page.WaitForAssertion(() => Assert.Contains(
            "Read the two plans again",
            page.FindAll(".bead-held .bead-row-title").Select(row => row.TextContent.Trim())));
    }

    [Fact]
    public void KeepsTheQuickCreateOpenWithTheTitleAndTheReasonWhenBdRefusedTheCreate()
    {
        var page = ThePageOfTheEpicThatTakesACreate();
        projects.Bd.Fails(TheCreateOfTheNewBead, "unknown issue type \"task\"");

        page.Find(".bead-held-add").Click();
        page.Find("#held-create-title").Input("Read the two plans again");
        page.Find(".bead-held-create-write").Click();

        Assert.Single(page.FindAll("#held-create-title"));
        Assert.Equal("Read the two plans again", page.Find("#held-create-title").GetAttribute("value"));
        Assert.Contains(
            "unknown issue type",
            page.Find(".bead-held-create .bead-write-message").TextContent,
            StringComparison.Ordinal);
    }

    [Fact]
    public void ClosesTheQuickCreateOfAHeldBeadOnEscapeAndRunsNoCreate()
    {
        var page = ThePageOfTheEpicThatTakesACreate();

        page.Find(".bead-held-add").Click();
        page.Find("#held-create-title").Input("Read the two plans again");
        page.Find("#held-create-title").KeyDown(Key.Escape);

        Assert.Empty(page.FindAll("#held-create-title"));
        Assert.Single(page.FindAll(".bead-held-add"));
        Assert.DoesNotContain(
            projects.Bd.Invocations,
            run => run.StartsWith("create --title", StringComparison.Ordinal));
    }

    [Fact]
    public void DisablesTheQuickCreateOfAHeldBeadWhenTheInstalledBdCannotCreateInsideAnEpic()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints("create --help", """
                Flags:
                      --silent          Output only the issue ID (for scripting)
                      --title string    Issue title
                  -t, --type string     Issue type
                """);
        var page = ThePageOfTheEpic();

        page.WaitForAssertion(() =>
            Assert.True(page.Find(".bead-held-add").HasAttribute("disabled")));
        Assert.Contains(
            "--parent",
            page.Find(".bead-held-create").GetAttribute("title") ?? string.Empty,
            StringComparison.Ordinal);
    }

    [Fact]
    public void DrawsTheBeadsOfBothDirectionsOfTheDependenciesAsThatSameRow()
    {
        var page = ThePageOfTheBeadWithEveryFact();

        var rows = page.FindAll(".bead-edge");
        Assert.Equal(
            ["Choose a registrar", "Launch the site"],
            rows.Select(row => TheOneIn(".bead-row-title", row).TextContent.Trim()));
        Assert.All(rows, row => Assert.NotNull(row.QuerySelector(".bead-dot")));
        Assert.All(rows, row => Assert.NotNull(row.QuerySelector(".bead-edge-cut")));
        Assert.Equal(
            ["task", "b-9", "feature", "b-10"],
            rows.SelectMany(row => row.QuerySelectorAll("code.machine-text-quiet"))
                .Select(one => one.TextContent.Trim()));
    }

    [Fact]
    public void AsksBeforeItCutsAnEdgeAndCutsNothingWhenThePersonCancels()
    {
        var page = ThePageOfTheBeadWhoseEdgesBdCuts();

        TheCut(page, "Choose a registrar").Click();

        var row = page.FindAll(".bead-edge")[0];
        Assert.Contains("Cut this edge?", row.TextContent, StringComparison.Ordinal);
        TheOneIn(".bead-edge-cancel", row).Click();
        Assert.Empty(page.FindAll(".bead-edge-cancel"));
        Assert.NotNull(page.FindAll(".bead-edge")[0].QuerySelector(".bead-row-title"));
        Assert.DoesNotContain(
            projects.Bd.Invocations,
            run => run.StartsWith("dep remove", StringComparison.Ordinal));
    }

    [Fact]
    public void CutsTheEdgeOfEitherDirectionWhenThePersonAnswersYes()
    {
        var page = ThePageOfTheBeadWhoseEdgesBdCuts();

        TheCut(page, "Choose a registrar").Click();
        page.Find(".bead-edge-yes").Click();
        TheCut(page, "Launch the site").Click();
        page.Find(".bead-edge-yes").Click();

        Assert.Equal(
            ["dep remove b-7 b-9", "dep remove b-10 b-7"],
            projects.Bd.Invocations.Where(run => run.StartsWith("dep remove", StringComparison.Ordinal)));
    }

    [Fact]
    public void StandsNoBlockerPickerOnThePageUntilAPressAsksForOne()
    {
        var page = ThePageOfTheBeadWhoseEdgesBdCuts();

        Assert.Empty(page.FindAll("#write-blocker"));
        page.Find(".bead-blocker-press").Click();
        Assert.Single(page.FindAll("#write-blocker"));
    }

    [Fact]
    public void AddsTheBlockerThatAPickOfTheOpenPickerNames()
    {
        var page = ThePageOfTheBeadWhoseEdgesBdCuts();

        page.Find(".bead-blocker-press").Click();
        page.Find("#write-blocker").Change("b-2");

        Assert.Contains("dep add b-7 b-2", projects.Bd.Invocations);
        Assert.Empty(page.FindAll("#write-blocker"));
    }

    [Fact]
    public void KeepsTheBlockerPickerOpenWhenBdRefusesTheEdgeThatAPickAsksFor()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Fails("dep add b-7 b-2", "that edge would make a cycle");
        var page = ThePageOfTheBeadWithEveryFact();

        page.Find(".bead-blocker-press").Click();
        page.Find("#write-blocker").Change("b-2");

        Assert.Single(page.FindAll("#write-blocker"));
        Assert.Contains("cycle", page.Find(".bead-write-message").TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void ClosesTheBlockerPickerOnEscapeAndRunsNoCommand()
    {
        var page = ThePageOfTheBeadWhoseEdgesBdCuts();

        page.Find(".bead-blocker-press").Click();
        page.Find("#write-blocker").KeyDown(Key.Escape);

        Assert.Empty(page.FindAll("#write-blocker"));
        Assert.Single(page.FindAll(".bead-blocker-press"));
        Assert.DoesNotContain(
            projects.Bd.Invocations,
            run => run.StartsWith("dep add", StringComparison.Ordinal));
    }

    [Fact]
    public void DrawsOneLineForTheBlockerTheDependentAndTheHeldBeadThatABeadHasNoneOf()
    {
        var page = ThePageOfTheBareBead();

        var line = page.FindAll(".bead-prose-column .bead-absent")[0];
        Assert.Equal(
            "No bead blocks this one, it blocks no other bead, and it holds none.",
            TheOneIn("span", line).TextContent.Trim());
        Assert.NotNull(line.QuerySelector(".bead-blocker-press"));
        Assert.NotNull(line.QuerySelector(".bead-held-add"));
        Assert.DoesNotContain(
            "Dependencies",
            page.FindAll(".bead-prose-column .bead-box")
                .Select(box => TheOneIn("h2", box).TextContent.Trim()));
    }

    [Theory]
    [InlineData(TheBareBeadWithABlocker, TheBacklogOfABeadWithABlocker)]
    [InlineData(TheBareBead, TheBacklogOfABeadWithADependent)]
    [InlineData(TheBareBead, TheBacklogOfABeadWithAHeldBead)]
    public void DrawsTheDependencyBoxesWhenTheBeadNamesAnyOneOfTheThree(string bead, string backlog)
    {
        var page = TheDetailPageOf("b-7", bead, "[]", backlog);

        Assert.Contains(
            "Dependencies",
            page.FindAll(".bead-prose-column .bead-box")
                .Select(box => TheOneIn("h2", box).TextContent.Trim()));
    }

    [Fact]
    public void MakesTheFirstHeldBeadFromThePressOfTheLineThatSaysTheBeadHoldsNone()
    {
        var page = ThePageOfTheBareBead();

        page.Find(".bead-absent .bead-held-add").Click();
        page.Find(".bead-absent #held-create-title").Input("Read the two plans");
        page.Find(".bead-absent .bead-held-create-write").Click();

        Assert.Contains(
            "create --title Read the two plans --type task --parent b-7 --silent",
            projects.Bd.Invocations);
    }

    [Fact]
    public void CarriesThePressThatMakesTheFirstHeldBeadOnItsOwnLineWhenABeadBlocksThisOne()
    {
        projects.Bd.DeclaresEveryWrite();
        var page = TheDetailPageOf("b-7", TheBareBeadWithABlocker, "[]", TheBacklogOfABeadWithABlocker);

        var line = page.FindAll(".bead-prose-column .bead-absent")[0];
        Assert.Equal("This bead holds no bead.", TheOneIn("span", line).TextContent.Trim());
        Assert.NotNull(line.QuerySelector(".bead-held-add"));
        Assert.Contains(
            "Dependencies",
            page.FindAll(".bead-prose-column .bead-box")
                .Select(box => TheOneIn("h2", box).TextContent.Trim()));
    }

    [Fact]
    public void OpensTheBlockerPickerOnThePressOfTheLineThatNamesTheAbsentBeads()
    {
        var page = ThePageOfTheBareBead();

        page.Find(".bead-absent .bead-blocker-press").Click();

        Assert.Single(page.FindAll(".bead-absent #write-blocker"));
    }

    [Fact]
    public void DrawsOneLineForTheAcceptanceCriteriaAndTheNotesThatABeadStatesNeitherOf()
    {
        var page = ThePageOfTheBareBead();

        var line = page.FindAll(".bead-prose-column .bead-absent")[1];
        Assert.Equal(
            "This bead states no acceptance criteria and carries no notes.",
            TheOneIn("span", line).TextContent.Trim());
        Assert.NotNull(line.QuerySelector(".bead-acceptance-add"));
        Assert.NotNull(line.QuerySelector(".bead-notes-add"));
        Assert.Equal(
            ["Description", "Comments"],
            page.FindAll(".bead-prose-column .bead-box")
                .Select(box => TheOneIn("h2", box).TextContent.Trim()));
    }

    [Theory]
    [InlineData(TheBareBeadWithAcceptanceCriteria)]
    [InlineData(TheBareBeadWithNotes)]
    public void DrawsTheAcceptanceCriteriaAndTheNotesAsBoxesWhenTheBeadStatesEither(string bead)
    {
        var page = TheDetailPageOf("b-7", bead, "[]", TheBacklogOfTheBareBead);

        var headings = page.FindAll(".bead-prose-column .bead-box")
            .Select(box => TheOneIn("h2", box).TextContent.Trim())
            .ToArray();
        Assert.Contains("Acceptance criteria", headings);
        Assert.Contains("Notes", headings);
    }

    [Fact]
    public void OpensTheNotesBoxOnThePressOfTheLineThatSaysTheBeadCarriesNone()
    {
        var page = ThePageOfTheBareBead();

        page.Find(".bead-absent .bead-notes-add").Click();

        Assert.Single(page.FindAll("#notes-text"));
        Assert.Empty(page.FindAll(".bead-notes-caution"));
    }

    [Fact]
    public void OpensTheAcceptanceCriteriaBoxOnThePressOfTheLineThatSaysTheBeadStatesNone()
    {
        var page = ThePageOfTheBareBead();

        page.Find(".bead-absent .bead-acceptance-add").Click();

        Assert.Single(page.FindAll("#prose-acceptance"));
    }

    [Fact]
    public void WritesTheAcceptanceCriteriaThatAPersonTypedInTheBoxThatTheLineOpened()
    {
        var page = ThePageOfTheBareBead();

        page.Find(".bead-absent .bead-acceptance-add").Click();
        page.Find("#prose-acceptance").Input("One plan wins.");
        page.Find(".bead-acceptance-save").Click();

        Assert.Contains("update b-7 --acceptance One plan wins.", projects.Bd.Invocations);
    }

    [Fact]
    public void DrawsTheLineAgainWhenAPersonClosesTheBoxThatItOpenedAndWritesNothing()
    {
        var page = ThePageOfTheBareBead();

        page.Find(".bead-absent .bead-acceptance-add").Click();
        page.Find(".bead-acceptance-edit .btn-outline-secondary").Click();

        Assert.Single(page.FindAll(".bead-absent .bead-acceptance-add"));
        Assert.Empty(page.FindAll("#prose-acceptance"));
    }

    [Fact]
    public void OpensTheAcceptanceCriteriaBoxOnAPressOfTheOnesThatTheBeadStates()
    {
        projects.Bd.DeclaresEveryWrite();
        var page = TheDetailPageOf("b-7", TheBareBeadWithAcceptanceCriteria, "[]", TheBacklogOfTheBareBead);

        page.Find(".bead-acceptance-press").Click();

        Assert.Single(page.FindAll("#prose-acceptance"));
    }

    [Fact]
    public void SaysInTheDescriptionBoxThatABeadWithNoDescriptionHasNone()
    {
        var page = TheDetailPageOf("b-7", TheBeadOfNoProseAtAll, "[]", TheBacklogOfTheBareBead);

        var first = page.FindAll(".bead-prose-column .bead-box")[0];
        Assert.Equal("Description", TheOneIn("h2", first).TextContent.Trim());
        var missing = TheOneIn(".bead-prose-missing", first);
        Assert.Equal("This bead has no description.", missing.TextContent.Trim());
        Assert.DoesNotContain("text-muted", missing.ClassList);
    }

    [Fact]
    public void StatesTheFailedReadOfTheBacklogInOneLineAboveTheColumnsAndNamesWhatItCannotSay()
    {
        var page = ThePageOfABeadWhoseBacklogBdCannotRead();

        var line = page.Find(".bead-unread-backlog");
        Assert.Contains("no beads database found", line.TextContent, StringComparison.Ordinal);
        Assert.Contains("epic", line.TextContent, StringComparison.Ordinal);
        Assert.Contains("blocks", line.TextContent, StringComparison.Ordinal);
        Assert.Contains("holds", line.TextContent, StringComparison.Ordinal);
        Assert.DoesNotContain("status", line.TextContent, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("bead-columns", line.NextElementSibling?.ClassName);
    }

    [Fact]
    public void DrawsNoBeadBoxAndNoSecondCopyOfTheFailureInTheProseColumnWhenBdGaveNoBacklog()
    {
        var page = ThePageOfABeadWhoseBacklogBdCannotRead();

        Assert.DoesNotContain(
            page.FindAll(".bead-prose-column .bead-box")
                .Select(box => TheOneIn("h2", box).TextContent.Trim()),
            heading => heading is "Dependencies" or "Held beads");
        Assert.Single(page.FindAll(".bead-message"));
        Assert.Equal(
            1,
            page.Markup.Split("no beads database found", StringSplitOptions.None).Length - 1);
        Assert.Empty(page.FindAll(".bead-blocker-press"));
    }

    [Fact]
    public void DrawsTheStatusBoxAndNoEpicBoxInTheFactStripWhenBdGaveNoBacklog()
    {
        var page = ThePageOfABeadWhoseBacklogBdCannotRead();

        Assert.Equal(
            ["Status", "Priority", "Type", "Labels"],
            page.FindAll(".bead-fact-strip .bead-fact")
                .Select(fact => TheOneIn(".bead-fact-name", fact).TextContent.Trim()));
    }

    [Fact]
    public void StatesTheStatusThatBdStoredOnTheBeadWhenBdGaveNoBacklog()
    {
        var page = ThePageOfABeadWhoseBacklogBdCannotRead();

        var status = page.FindAll(".bead-fact-strip .bead-fact")[0];
        Assert.Equal("open", TheOneIn(".bead-fact-value", status).TextContent.Trim());
    }

    [Fact]
    public void OffersTheFourStoredStatusesInTheStandingStatusBoxWhenBdGaveNoBacklog()
    {
        var page = ThePageOfABeadWhoseBacklogBdCannotReadAndThatBdWrites();

        ThePress(page, "Status, open").Click();

        Assert.Equal(
            ["open", "in progress", "deferred", "closed"],
            page.FindAll(".bead-fact-picker .bead-fact-choice").Select(entry => entry.TextContent.Trim()));
    }

    [Fact]
    public void SetsTheStatusFromTheStandingStatusBoxWhenBdGaveNoBacklog()
    {
        var page = ThePageOfABeadWhoseBacklogBdCannotReadAndThatBdWrites();

        ThePress(page, "Status, open").Click();
        ThePick(page, "in progress").Click();

        Assert.Contains("update b-7 --status in_progress", projects.Bd.Invocations);
    }

    [Fact]
    public void DefersTheBeadFromTheStandingStatusBoxWhenBdGaveNoBacklog()
    {
        var page = ThePageOfABeadWhoseBacklogBdCannotReadAndThatBdWrites();

        ThePress(page, "Status, open").Click();
        ThePick(page, "deferred").Click();

        Assert.Contains("defer b-7", projects.Bd.Invocations);
    }

    [Fact]
    public void ClosesTheBeadWithAReasonFromTheStandingStatusBoxWhenBdGaveNoBacklog()
    {
        var page = ThePageOfABeadWhoseBacklogBdCannotReadAndThatBdWrites();

        ThePress(page, "Status, open").Click();
        ThePick(page, "closed").Click();
        page.Find(".bead-fact-answer").Input("The vendor answered.");
        page.Find(".bead-fact-commit").Click();

        Assert.Contains("close b-7 --reason The vendor answered.", projects.Bd.Invocations);
    }

    [Fact]
    public void NamesTheReasonAndDrawsNoColumnsWhenBdWillNotShowTheBead()
    {
        var page = ThePageOfABeadThatBdWillNotShow();

        Assert.Contains(
            "issue not found: b-7",
            page.Find("p.bead-message").TextContent,
            StringComparison.Ordinal);
        Assert.Empty(page.FindAll(".bead-columns"));
    }

    [Fact]
    public void SaysNothingAboutTheBacklogAboveTheColumnsWhenBdListedIt()
    {
        var page = ThePageOfTheBeadWithEveryFact();

        Assert.Empty(page.FindAll(".bead-unread-backlog"));
    }

    [Fact]
    public void DrawsTheCloseReasonOfAClosedBeadAsTheFirstBoxOfTheProseColumn()
    {
        var page = ThePageOfTheBead(TheClosedBead, TheComments);

        var first = page.FindAll(".bead-prose-column .bead-box")[0];
        Assert.Equal("Closed", TheOneIn("h2", first).TextContent.Trim());
        Assert.Contains("The vendor answered.", first.TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void DrawsEachCommentAsABoxAndPutsTheCommentBoxAtTheFootOfTheComments()
    {
        var page = ThePageOfTheBead(TheBeadWithEveryFact, TheComments);

        var comments = page.FindAll(".bead-box .bead-comment");
        Assert.Equal(["Read the two plans again."], comments.Select(one => TheOneIn(".bead-comment-text", one).TextContent));
        var parts = page.FindAll(".bead-prose-column .bead-box")[^1].Children;
        var lastComment = parts.ToList().FindLastIndex(part => part.ClassList.Contains("bead-comment"));
        var box = parts.ToList().FindIndex(part => part.QuerySelector("#write-comment") is not null);
        Assert.True(lastComment >= 0 && lastComment < box);
    }

    [Fact]
    public void PutsTheOneCommentBoxOfThePageInTheProseColumn()
    {
        var page = ThePageOfTheBead(TheBeadWithEveryFact, TheComments);

        Assert.Single(page.FindAll("#write-comment"));
        Assert.Single(page.FindAll(".bead-prose-column #write-comment"));
    }

    [Fact]
    public void SaysWhyInsteadOfTheCommentsWhenBdWillNotReadThem()
    {
        var page = ThePageOfABeadWhoseCommentsBdCannotRead();

        var box = page.FindAll(".bead-prose-column .bead-box")[^1];
        Assert.Contains("unknown command", TheOneIn(".bead-message", box).TextContent, StringComparison.Ordinal);
        Assert.Empty(page.FindAll(".bead-comment"));
        Assert.Single(page.FindAll("#write-comment"));
    }

    [Fact]
    public void SaysThatABeadCarriesNoCommentWhenBdReadsAnEmptyListOfThem()
    {
        var page = ThePageOfTheBead(TheBeadWithEveryFact, "[]");

        var box = page.FindAll(".bead-prose-column .bead-box")[^1];
        Assert.Equal("This bead carries no comment.", TheOneIn(".text-muted", box).TextContent.Trim());
        Assert.Empty(page.FindAll(".bead-comment"));
        Assert.Empty(page.FindAll(".bead-prose-column .bead-message"));
    }

    [Fact]
    public void PressesEveryFactOfTheStripAndStatesTheFieldAndTheValueToAReader()
    {
        var page = ThePageOfTheBeadWithEveryFact();

        var presses = page.FindAll(".bead-fact-value button");
        Assert.Equal(
            ["Status, needs you", "Priority, p2", "Type, task", "Labels, human", "Epic, Ship the site"],
            presses.Select(press => press.GetAttribute("aria-label")));
        Assert.Equal(
            ["needs you", "p2", "task", "human", "Ship the site"],
            presses.Select(press => press.TextContent.Trim()));
    }

    [Fact]
    public void OffersTheFourStoredStatusesInOnePickerWhereBdGivesThreeVerbs()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Status, needs you").Click();

        Assert.Equal(
            ["open", "in progress", "deferred", "closed"],
            page.FindAll(".bead-fact-picker .bead-fact-choice").Select(entry => entry.TextContent.Trim()));
    }

    [Fact]
    public void MarksTheStoredStatusThatTheBeadIsInAmongTheEntriesOfItsPicker()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Status, needs you").Click();

        var current = page.FindAll(".bead-fact-picker .bead-fact-choice")
            .Where(entry => string.Equals(entry.GetAttribute("aria-current"), "true", StringComparison.Ordinal));
        Assert.Equal(["open"], current.Select(entry => entry.TextContent.Trim()));
    }

    [Fact]
    public void SetsTheStatusOfTheBeadOnAPickOfInProgress()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Status, needs you").Click();
        ThePick(page, "in progress").Click();

        Assert.Contains("update b-7 --status in_progress", projects.Bd.Invocations);
        Assert.Empty(page.FindAll(".bead-fact-strip .bead-fact-picker"));
    }

    [Fact]
    public void StatesWhatABdWithoutTheCloseLacksInsteadOfAStatusPickerThatCannotClose()
    {
        var page = ThePageOfTheBeadThatBdCannotClose();

        ThePress(page, "Status, needs you").Click();

        Assert.NotEmpty(page.FindAll(".bead-fact-picker .bead-fact-refusal"));
        Assert.Empty(page.FindAll(".bead-fact-picker .bead-fact-choice"));
    }

    [Fact]
    public void AsksWhyTheWorkEndedOnAPickOfClosedAndRunsNoCommandWhileTheReasonIsEmpty()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Status, needs you").Click();
        ThePick(page, "closed").Click();

        Assert.Equal("Why the work ended", page.Find(".bead-fact-answer").GetAttribute("aria-label"));
        Assert.True(page.Find(".bead-fact-commit").HasAttribute("disabled"));
        Assert.DoesNotContain(
            projects.Bd.Invocations,
            command => command.StartsWith("close b-7", StringComparison.Ordinal));
    }

    [Fact]
    public void ClosesTheBeadWithTheReasonThatThePersonTypedIntoTheStatusControl()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Status, needs you").Click();
        ThePick(page, "closed").Click();
        page.Find(".bead-fact-answer").Input("The vendor answered.");
        page.Find(".bead-fact-commit").Click();

        Assert.Contains("close b-7 --reason The vendor answered.", projects.Bd.Invocations);
        Assert.Empty(page.FindAll(".bead-fact-strip .bead-fact-picker"));
    }

    [Fact]
    public void DefersTheBeadWithTheCommandOfItsOwnOnAPickOfDeferred()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Status, needs you").Click();
        ThePick(page, "deferred").Click();

        Assert.Contains("defer b-7", projects.Bd.Invocations);
        Assert.DoesNotContain("update b-7 --status deferred", projects.Bd.Invocations);
    }

    [Fact]
    public void ReopensAClosedBeadOnAPickOfOpenInTheSamePicker()
    {
        var page = ThePageOfTheClosedBeadThatBdWrites();

        ThePress(page, "Status, closed").Click();
        ThePick(page, "open").Click();

        Assert.Contains("update b-7 --status open", projects.Bd.Invocations);
    }

    [Fact]
    public void ShowsTheNewPriorityAndSaysNothingBesideItAfterAPickThatBdTook()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Priority, p2").Click();
        ThePick(page, "p1").Click();

        Assert.Contains("update b-7 --priority 1", projects.Bd.Invocations);
        Assert.Equal("p1", ThePress(page, "Priority, p1").TextContent.Trim());
        Assert.Empty(page.FindAll(".bead-fact-strip .bead-fact-picker"));
        Assert.DoesNotContain("bd made the change", page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void ClosesThePickerOnEscapeAndRunsNoCommandAndPutsTheKeyboardBackOnTheValue()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Type, task").Click();
        var thePicker = TheReferenceOf(page.Find(".bead-fact-picker"));
        page.Find(".bead-fact-picker").KeyDown(Key.Escape);

        Assert.Empty(page.FindAll(".bead-fact-strip .bead-fact-picker"));
        Assert.DoesNotContain(
            projects.Bd.Invocations,
            command => command.StartsWith("update b-7", StringComparison.Ordinal));
        Assert.Equal([thePicker, TheReferenceOf(ThePress(page, "Type, task"))], TheFocused());
    }

    [Fact]
    public void KeepsThePickerOpenAndStatesTheReasonWhenBdRefusesTheWrite()
    {
        var page = ThePageOfTheBeadThatBdWrites();
        projects.Bd.Fails("update b-7 --type chore", "unknown type \"chore\"");

        ThePress(page, "Type, task").Click();
        ThePick(page, "chore").Click();

        Assert.Contains(
            "unknown type",
            page.Find(".bead-fact-picker .bead-write-message").TextContent,
            StringComparison.Ordinal);
        Assert.Empty(page.FindAll(".bead-fact-picker .bead-fact-refusal"));
        Assert.NotEmpty(page.FindAll(".bead-fact-picker .bead-fact-choice"));
    }

    [Fact]
    public void OpensOnAPressAndStatesWhatABdWithoutTheWriteLacksInsteadOfAPicker()
    {
        var page = ThePageOfTheBead(TheBeadWithEveryFact, "[]");

        ThePress(page, "Priority, p2").Click();

        Assert.NotEmpty(page.FindAll(".bead-fact-picker .bead-fact-refusal"));
        Assert.Empty(page.FindAll(".bead-fact-picker .bead-fact-choice"));
        Assert.DoesNotContain(
            projects.Bd.Invocations,
            command => command.StartsWith("update b-7", StringComparison.Ordinal));
    }

    [Fact]
    public void OpensAOneLineBoxOnAPressOfTheTitleAndNoBoxForTheDescription()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        page.Find(".bead-title-press").Click();

        Assert.Equal("INPUT", page.Find(".bead-title-box").TagName);
        Assert.NotEmpty(page.FindAll("h1 .bead-title-box"));
        Assert.Empty(page.FindAll(".bead-prose-editor"));
        Assert.Empty(page.FindAll(".bead-prose-preview"));
    }

    [Fact]
    public void SendsTheDescriptionUnchangedWhenAPersonWritesTheTitleAloneAndShowsItInTheHead()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        page.Find(".bead-title-press").Click();
        page.Find(".bead-title-box").Input("A sharper title");
        page.Find(".bead-title-save").Click();

        Assert.Contains(TheWriteOfASharperTitle, projects.Bd.Invocations);
        Assert.Equal("A sharper title", page.Find(".bead-head .bead-title-press").TextContent.Trim());
    }

    [Fact]
    public void OpensTheDescriptionBoxWithItsPreviewBesideItAndNoBoxForTheTitle()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        page.Find(".bead-prose-press").Click();

        Assert.Equal("TEXTAREA", page.Find(".bead-prose-editor").TagName);
        Assert.NotNull(page.Find(".bead-prose-preview"));
        Assert.Empty(page.FindAll(".bead-title-box"));
    }

    [Fact]
    public void DrawsWhatThePersonTypesIntoTheDescriptionBoxAsProseInThePreviewBesideIt()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        page.Find(".bead-prose-press").Click();
        page.Find(".bead-prose-editor").Input("## Demo\nA person reads it.");

        var preview = page.Find(".bead-prose-preview");
        Assert.Equal(["Demo"], preview.QuerySelectorAll("h2").Select(one => one.TextContent.Trim()));
        Assert.Contains("A person reads it.", preview.TextContent, StringComparison.Ordinal);
    }

    [Fact]
    public void SendsTheTitleUnchangedWhenAPersonWritesTheDescriptionAlone()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        page.Find(".bead-prose-press").Click();
        page.Find(".bead-prose-editor").Input("Three plans remain.");
        page.Find(".bead-prose-save").Click();

        Assert.Contains(
            "update b-7 --title Pick a hosting plan --description Three plans remain.",
            projects.Bd.Invocations);
    }

    [Fact]
    public void OpensTheDescriptionBoxOnAPressOfTheProseItself()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        page.Find(".bead-prose-pressable").Click();

        Assert.NotEmpty(page.FindAll(".bead-prose-editor"));
    }

    [Fact]
    public void ClosesTheTitleBoxOnEscapeAndRunsNoCommandAndPutsTheKeyboardBackOnTheTitle()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        page.Find(".bead-title-press").Click();
        page.Find(".bead-title-box").Input("A sharper title");
        page.Find(".bead-title-edit").KeyDown(Key.Escape);

        Assert.Empty(page.FindAll(".bead-title-box"));
        Assert.DoesNotContain(
            projects.Bd.Invocations,
            command => command.StartsWith("update b-7 --title", StringComparison.Ordinal));
        Assert.Equal(TheTitleOfThatBead, page.Find(".bead-title-press").TextContent.Trim());
    }

    [Fact]
    public void StatesWhatABdWithoutTheProseWriteLacksInsteadOfABoxOnTheTitleAndOnTheDescription()
    {
        var page = ThePageOfTheBead(TheBeadWithEveryFact, "[]");

        page.Find(".bead-title-press").Click();
        Assert.NotEmpty(page.FindAll(".bead-title-refusal"));
        Assert.Empty(page.FindAll(".bead-title-box"));
        Assert.Equal(TheTitleOfThatBead, page.Find(".bead-head h1").TextContent.Trim());

        page.Find(".bead-prose-press").Click();
        Assert.NotEmpty(page.FindAll(".bead-prose-refusal"));
        Assert.Empty(page.FindAll(".bead-prose-editor"));
    }

    [Fact]
    public void KeepsTheDeliberateRewriteAndItsCautionOnTheNotes()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        Assert.Empty(page.FindAll(".bead-notes-caution"));
        Assert.Equal("Rewrite the notes", page.Find(".bead-notes-press").TextContent.Trim());

        page.Find(".bead-notes-press").Click();

        Assert.NotEmpty(page.FindAll(".bead-notes-caution"));
        Assert.NotEmpty(page.FindAll("#notes-text"));
    }

    [Fact]
    public void DrawsNoTriageSectionBecauseEveryControlStandsBesideTheValueThatItChanges()
    {
        var page = ThePageOfTheBead(TheBeadWithEveryFact, "[]");

        Assert.Empty(page.FindAll(".bead-triage"));
        Assert.DoesNotContain("Triage", page.Markup, StringComparison.Ordinal);
    }

    [Fact]
    public void ShowsTheNewTypeAfterAPickThatBdTook()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Type, task").Click();
        ThePick(page, "feature").Click();

        Assert.Contains("update b-7 --type feature", projects.Bd.Invocations);
        Assert.Equal("feature", ThePress(page, "Type, feature").TextContent.Trim());
    }

    [Fact]
    public void PutsTheValueAndEveryEntryOfItsPickerInTheTabOrderSoThatTheKeyboardAloneReachesThem()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        var press = ThePress(page, "Priority, p2");
        Assert.Equal("BUTTON", press.TagName);
        Assert.Null(press.GetAttribute("tabindex"));

        press.Click();

        var entries = page.FindAll(".bead-fact-picker .bead-fact-choice");
        Assert.NotEmpty(entries);
        Assert.All(entries, entry => Assert.Equal("BUTTON", entry.TagName));
        Assert.All(entries, entry => Assert.Null(entry.GetAttribute("tabindex")));
    }

    [Fact]
    public void ListsEveryLabelOfTheProjectAndTicksTheOnesThatThisBeadCarries()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Labels, human").Click();

        var entries = page.FindAll(".bead-fact-picker .bead-fact-choice");
        Assert.Equal(["docs", "human"], entries.Select(TheWordsOf));
        Assert.Equal(["false", "true"], entries.Select(entry => entry.GetAttribute("aria-pressed")));
        Assert.Equal(
            ["human"],
            entries.Where(entry => entry.QuerySelector(".bead-fact-tick") is not null).Select(TheWordsOf));
    }

    [Fact]
    public void PutsALabelOfTheProjectOnTheBeadOnAPressOfItsEntryAndTicksItWithoutASecondPress()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Labels, human").Click();
        ThePick(page, "docs").Click();

        Assert.Contains("label add b-7 docs", projects.Bd.Invocations);
        Assert.Equal(
            ["docs", "human"],
            page.FindAll(".bead-fact-picker .bead-fact-choice")
                .Where(entry => entry.QuerySelector(".bead-fact-tick") is not null)
                .Select(TheWordsOf));
    }

    [Fact]
    public void TakesALabelOffTheBeadOnAPressOfTheEntryThatItCarries()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Labels, human").Click();
        ThePick(page, "human").Click();

        Assert.Contains("label remove b-7 human", projects.Bd.Invocations);
    }

    [Fact]
    public void AddsALabelThatTheProjectDoesNotUseYetFromTheBoxAtTheFootOfTheList()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Labels, human").Click();
        Assert.True(page.Find(".bead-fact-add").HasAttribute("disabled"));
        page.Find(".bead-fact-new").Input("spike");
        page.Find(".bead-fact-add").Click();

        Assert.Contains("label add b-7 spike", projects.Bd.Invocations);
    }

    [Fact]
    public void WritesTheSpellingOfTheProjectWhenTheBoxTakesALabelThatDiffersFromItInCaseAlone()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Labels, human").Click();
        page.Find(".bead-fact-new").Input("DOCS");
        page.Find(".bead-fact-add").Click();

        Assert.Contains("label add b-7 docs", projects.Bd.Invocations);
        Assert.DoesNotContain("label add b-7 DOCS", projects.Bd.Invocations);
    }

    [Fact]
    public void WritesNothingAndSaysSoWhenTheBoxTakesALabelThatTheBeadAlreadyCarries()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Labels, human").Click();
        page.Find(".bead-fact-new").Input("Human");
        page.Find(".bead-fact-add").Click();

        Assert.DoesNotContain(
            projects.Bd.Invocations,
            command => command.StartsWith("label add b-7", StringComparison.Ordinal));
        Assert.Contains(
            "already carries human",
            page.Find(".bead-fact-picker .bead-write-message").TextContent,
            StringComparison.Ordinal);
    }

    [Fact]
    public void OffersEveryEpicOfTheBacklogAndANoEpicEntryAndMarksTheOneThatHoldsThisBead()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Epic, Ship the site").Click();

        var entries = page.FindAll(".bead-fact-picker .bead-fact-choice");
        Assert.Equal(["no epic", "Choose the vendor", "Ship the site"], entries.Select(TheWordsOf));
        Assert.Equal(
            ["Ship the site"],
            entries.Where(entry => entry.GetAttribute("aria-current") is "true").Select(TheWordsOf));
    }

    [Fact]
    public void LinksToTheEpicBesideThePressThatMovesTheBeadIntoAnother()
    {
        var page = ThePageOfTheBeadWithEveryFact();

        var link = page.Find(".bead-fact-page");
        Assert.Equal("bead/b-1", link.GetAttribute("href"));
        Assert.Equal("Open Ship the site", link.GetAttribute("aria-label"));
    }

    [Fact]
    public void MovesTheBeadIntoTheEpicThatThePersonPickedWithNoSecondPress()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Epic, Ship the site").Click();
        ThePick(page, "Choose the vendor").Click();

        Assert.Contains("update b-7 --parent b-2", projects.Bd.Invocations);
        Assert.Empty(page.FindAll(".bead-fact-strip .bead-fact-picker"));
    }

    [Fact]
    public void TakesTheBeadOutOfEveryEpicOnAPickOfNoEpic()
    {
        var page = ThePageOfTheBeadThatBdWrites();

        ThePress(page, "Epic, Ship the site").Click();
        ThePick(page, "no epic").Click();

        Assert.Contains("update b-7 --parent ", projects.Bd.Invocations);
    }

    // Throws so that no assertion reads past a value that is absent.
    private static IElement TheOneIn(string selector, IElement within) =>
        within.QuerySelector(selector) is { } found
            ? found
            : throw new InvalidOperationException($"The page drew no {selector}.");

    private static string TheWordsOf(IElement entry) =>
        TheOneIn(".bead-fact-words", entry).TextContent.Trim();

    // The elements that the page asked the browser to move the keyboard to, in order.
    private IReadOnlyList<string> TheFocused() =>
    [
        .. JSInterop.Invocations
            .Where(call => call.Identifier.EndsWith("focus", StringComparison.Ordinal))
            .Select(call => ((ElementReference)call.Arguments[0]!).Id),
    ];

    // The name that the browser knows this element by, which a move of the keyboard names.
    private static string TheReferenceOf(IElement element) =>
        element.Attributes
            .First(attribute =>
                attribute.Name.EndsWith("elementreference", StringComparison.Ordinal))
            .Value;

    private static IElement ThePress(IRenderedComponent<DetailPage> page, string accessibleName) =>
        page.Find($".bead-fact-value button[aria-label='{accessibleName}']");

    private static IElement ThePick(IRenderedComponent<DetailPage> page, string text) =>
        page.FindAll(".bead-fact-picker .bead-fact-choice")
            .Single(entry => string.Equals(TheWordsOf(entry), text, StringComparison.Ordinal));

    // The detail page of the bead that carries every fact, read from a bd that takes every write of
    // one bead. The write of the priority changes what a later read of the bead gives back, as a
    // real bd does, so the page can show what it read after the write.
    private IRenderedComponent<DetailPage> ThePageOfTheBeadThatBdWrites()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints("update b-7 --priority 1", string.Empty)
            .Prints("update b-7 --type feature", string.Empty)
            .Prints("update b-7 --status in_progress", string.Empty)
            .Prints("update b-7 --status open", string.Empty)
            .Prints("defer b-7", string.Empty)
            .Prints("label add b-7 docs", string.Empty)
            .After(
                "label add b-7 docs",
                bd => bd.PrintsIn(projects.Second.Value, "show b-7 --json", TheBeadOfTwoLabels))
            .Prints("label add b-7 spike", string.Empty)
            .Prints("label remove b-7 human", string.Empty)
            .Prints("update b-7 --parent b-2", string.Empty)
            .Prints("update b-7 --parent ", string.Empty)
            .Prints("close b-7 --reason The vendor answered.", string.Empty)
            .Prints(TheWriteOfASharperTitle, string.Empty)
            .After(
                TheWriteOfASharperTitle,
                bd => bd.PrintsIn(projects.Second.Value, "show b-7 --json", TheBeadOfASharperTitle))
            .Prints("update b-7 --title Pick a hosting plan --description Three plans remain.", string.Empty)
            .After(
                "update b-7 --type feature",
                bd => bd.PrintsIn(projects.Second.Value, "show b-7 --json", TheBeadOfTypeFeature))
            .After(
                "update b-7 --priority 1",
                bd => bd.PrintsIn(projects.Second.Value, "show b-7 --json", TheBeadAtPriorityOne));
        return ThePageOfTheBead(TheBeadWithEveryFact, "[]");
    }

    // The detail page of that bead, read from a bd that updates a status but has no close. The
    // status control needs three commands of bd, so a bd that lacks one of them can answer no
    // question that the control asks.
    private IRenderedComponent<DetailPage> ThePageOfTheBeadThatBdCannotClose()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints("--help", """
                Working With Issues:
                  comment           Add a comment to an issue
                  defer             Defer one or more issues for later
                  dep               Manage dependencies
                  label             Manage issue labels
                  update            Update one or more issues
                """);
        return ThePageOfTheBead(TheBeadWithEveryFact, "[]");
    }

    // The detail page of that bead, closed, read from a bd that takes every write of one bead, so
    // that a test presses the status of a bead which a person can reopen.
    private IRenderedComponent<DetailPage> ThePageOfTheClosedBeadThatBdWrites()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints("update b-7 --status open", string.Empty);
        return ThePageOfTheBead(TheClosedBead, "[]");
    }

    // The bead as bd gives it back after one write, which changes one field and leaves the rest.
    // Each caller states every field, so the one it moved stands out against its neighbours.
    private static string TheBeadBdGivesBack(
        string title,
        string type,
        int priority,
        IReadOnlyList<string> labels)
    {
        var quoted = string.Join(", ", labels.Select(label => $"\"{label}\""));
        return $$"""
            [{"id": "b-7", "title": "{{title}}", "issue_type": "{{type}}", "priority": {{priority}},
              "status": "open", "labels": [{{quoted}}], "parent": "b-1",
              "description": "Two plans remain."}]
            """;
    }

    private static string TheBeadOfTwoLabels =>
        TheBeadBdGivesBack("Pick a hosting plan", "task", 2, ["human", "docs"]);

    private const string TheWriteOfASharperTitle =
        "update b-7 --title A sharper title --description Two plans remain.";

    private static string TheBeadOfASharperTitle =>
        TheBeadBdGivesBack("A sharper title", "task", 2, ["human"]);

    private static string TheBeadOfTypeFeature =>
        TheBeadBdGivesBack("Pick a hosting plan", "feature", 2, ["human"]);

    private static string TheBeadAtPriorityOne =>
        TheBeadBdGivesBack("Pick a hosting plan", "task", 1, ["human"]);

    // The detail page of the bead that carries every fact, read from a bd that cuts either edge of
    // it. bd names the blocked bead first, so the two directions name the pair in opposite orders.
    private IRenderedComponent<DetailPage> ThePageOfTheBeadWhoseEdgesBdCuts()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints("dep remove b-7 b-9", string.Empty)
            .Prints("dep remove b-10 b-7", string.Empty)
            .Prints("dep add b-7 b-2", string.Empty);
        return ThePageOfTheBeadWithEveryFact();
    }

    private static IElement TheCut(IRenderedComponent<DetailPage> page, string title) =>
        page.FindAll(".bead-edge")
            .Single(row =>
                string.Equals(row.QuerySelector(".bead-row-title")?.TextContent.Trim(), title, StringComparison.Ordinal))
            .QuerySelector(".bead-edge-cut")!;

    // The detail page of the bare bead, read from a bd that takes every write of one bead, so that
    // the press of each line is one a person can use.
    private IRenderedComponent<DetailPage> ThePageOfTheBareBead()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints("dep add b-7 b-2", string.Empty)
            .Prints("update b-7 --notes The vendor answers slowly.", string.Empty)
            .Prints("create --title Read the two plans --type task --parent b-7 --silent", "b-7-1\n");
        return TheDetailPageOf("b-7", TheBareBead, "[]", TheBacklogOfTheBareBead);
    }

    private IRenderedComponent<DetailPage> ThePageOfTheBeadWithEveryFact() =>
        ThePageOfTheBead(TheBeadWithEveryFact, "[]");

    // The detail page of one bead of the second project, with these comments on it.
    private IRenderedComponent<DetailPage> ThePageOfTheBead(string bead, string comments) =>
        TheDetailPageOf("b-7", bead, comments, TheBacklogOfThatBead);

    // The detail page of one bead of the second project, read from a bd that shows that bead, its
    // comments and this backlog. The show and the backlog travel together, so neither drifts from
    // the other.
    private IRenderedComponent<DetailPage> TheDetailPageOf(
        string id,
        string bead,
        string comments,
        string backlog)
    {
        projects.Bd
            .PrintsIn(projects.Second.Value, $"show {id} --json", bead)
            .PrintsIn(projects.Second.Value, $"comments {id} --json", comments)
            .PrintsIn(projects.Second.Value, ListCommand, backlog)
            .PrintsIn(projects.First.Value, ListCommand, "[]");

        return TheRenderedDetailPageOf(id);
    }

    // The detail page of one bead of the second project, rendered against the bd that the test has
    // already scripted, at the address which names that project.
    private IRenderedComponent<DetailPage> TheRenderedDetailPageOf(string id)
    {
        projects.RegisterOn(Services);
        Services.AddSingleton(new BeadDetailReader(projects.Adapter, new BacklogReader(projects.Adapter)));

        Services.GetRequiredService<NavigationManager>()
            .NavigateTo($"bead/{id}?project={Uri.EscapeDataString(projects.Second.Value)}");

        return Render<DetailPage>(parameters => parameters.Add(page => page.Id, id));
    }

    // The detail page of the bare bead in a project whose backlog bd cannot read. Without the
    // backlog the app knows neither direction of the dependencies nor the beads that this one
    // holds, so no line may say that the bead names none of them.
    private IRenderedComponent<DetailPage> ThePageOfABeadWhoseBacklogBdCannotRead()
    {
        projects.Bd
            .PrintsIn(projects.Second.Value, "show b-7 --json", TheBareBead)
            .PrintsIn(projects.Second.Value, "comments b-7 --json", "[]")
            .Fails(ListCommand, "no beads database found")
            .Fails("list --json", "no beads database found");

        return TheRenderedDetailPageOf("b-7");
    }

    // The bare bead in a project whose backlog bd cannot read, from a bd that takes the three
    // commands behind the status box and nothing else.
    private IRenderedComponent<DetailPage> ThePageOfABeadWhoseBacklogBdCannotReadAndThatBdWrites()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints("update b-7 --status in_progress", string.Empty)
            .Prints("defer b-7", string.Empty)
            .Prints("close b-7 --reason The vendor answered.", string.Empty);

        return ThePageOfABeadWhoseBacklogBdCannotRead();
    }

    // The detail page of a bead that bd will not show. The show that failed is the one read this
    // page makes, because the reader asks for no backlog once it has no bead.
    private IRenderedComponent<DetailPage> ThePageOfABeadThatBdWillNotShow()
    {
        projects.Bd.Fails("show b-7 --json", "issue not found: b-7");

        return TheRenderedDetailPageOf("b-7");
    }

    // The detail page of a bead whose comments bd will not give. The bead and the backlog read as
    // they always do, so the page differs from a healthy one in the comments box alone.
    private IRenderedComponent<DetailPage> ThePageOfABeadWhoseCommentsBdCannotRead()
    {
        projects.Bd
            .PrintsIn(projects.Second.Value, "show b-7 --json", TheBeadWithEveryFact)
            .PrintsIn(projects.Second.Value, ListCommand, TheBacklogOfThatBead)
            .PrintsIn(projects.First.Value, ListCommand, "[]")
            .Fails("comments b-7 --json", "unknown command \"comments\" for \"bd\"");

        return TheRenderedDetailPageOf("b-7");
    }

    // The detail page of the epic that holds the bead of every fact, a closed bead, and, one level
    // further down, a bead of its own.
    private IRenderedComponent<DetailPage> ThePageOfTheEpic() =>
        TheDetailPageOf("b-1", $"[{TheRecordOfItsEpic}]", "[]", TheBacklogOfTheEpic);

    private IRenderedComponent<DetailPage> ThePageOfTheEpicThatTakesACreate()
    {
        projects.Bd.DeclaresEveryWrite();
        return ThePageOfTheEpic();
    }

    private IRenderedComponent<DetailPage> ThePageOfTheEpicThatMakesABeadInsideIt()
    {
        projects.Bd
            .DeclaresEveryWrite()
            .Prints(TheCreateOfTheNewBead, "b-1.1\n")
            .After(TheCreateOfTheNewBead, bd => bd.PrintsIn(
                projects.Second.Value,
                ListCommand,
                $"[{TheRecordsOfTheEpic}, {TheRecordOfTheNewBead}]"));
        return ThePageOfTheEpic();
    }

    private string TheAddress() => Services.GetRequiredService<NavigationManager>().Uri;

    private string TheAddressOfTheBead => $"bead/b-7?project={Uri.EscapeDataString(projects.Second.Value)}";

    private IRenderedComponent<DetailPage> ThePageAt(string address) =>
        ThePageAt(address, theActiveProject: null);

    // The detail page at this address, in a tab that holds this project or no project at all. Only
    // the second project holds the bead, so a page that reads another project shows nothing.
    private IRenderedComponent<DetailPage> ThePageAt(string address, ProjectPath? theActiveProject)
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

        Services.GetRequiredService<NavigationManager>().NavigateTo(address);

        return Render<DetailPage>(parameters => parameters.Add(page => page.Id, "b-7"));
    }

    protected override void Dispose(bool disposing)
    {
        projects.Dispose();
        base.Dispose(disposing);
    }
}
