using JidokaUi.Core.Beads;
using JidokaUi.Core.Jidoka;
using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Jidoka;

public sealed class JidokaPagesTests : IDisposable
{
    private readonly TempDirectory directory = new();
    private readonly ProjectPath project;
    private readonly string home;
    private readonly JidokaPages pages;

    public JidokaPagesTests()
    {
        project = ProjectPath.From(directory.CreateSubdirectory("shop"));
        home = directory.CreateSubdirectory("home");
        pages = new JidokaPages(new JidokaHome(home));
    }

    [Fact]
    public void ReadsTheQuestionPageInTheFolderOfTheRepositoryThatHoldsTheBead()
    {
        APageNamed("question-b-7.html", "<p>Pick one</p>");

        var served = pages.Read(JidokaPageKind.Question, new BeadAddress(project, "b-7"));

        Assert.Equal("<p>Pick one</p>", served?.Html);
    }

    [Fact]
    public void ReadsNothingWhenNoPageSitsBesideTheBead()
    {
        Assert.Null(pages.Read(JidokaPageKind.Question, new BeadAddress(project, "b-7")));
    }

    [Fact]
    public void ReadsNothingFromTheFolderOfAnotherRepository()
    {
        var elsewhere = Directory.CreateDirectory(Path.Combine(home, "pages", "other")).FullName;
        File.WriteAllText(Path.Combine(elsewhere, "question-b-7.html"), "<p>Not yours</p>");

        Assert.Null(pages.Read(JidokaPageKind.Question, new BeadAddress(project, "b-7")));
    }

    [Fact]
    public void ReadsTheCommitMessageSavedBesideTheGatePageAsItIsWritten()
    {
        APageNamed("gate-b-7-message.txt", "Add the site\n\nIt serves the shop.");

        Assert.Equal("Add the site\n\nIt serves the shop.", pages.SavedGateMessage(new BeadAddress(project, "b-7")));
    }

    [Fact]
    public void ReadsNoCommitMessageWhenNoneIsSaved()
    {
        Assert.Null(pages.SavedGateMessage(new BeadAddress(project, "b-7")));
    }

    [Fact]
    public void ReadsNoCommitMessageForAnIdThatIsNotAFileName()
    {
        APageNamed("gate-.-message.txt", "Out of reach");

        Assert.Null(pages.SavedGateMessage(new BeadAddress(project, ".")));
        Assert.Null(pages.SavedGateMessage(new BeadAddress(project, "a/b")));
    }

    [Fact]
    public void ListsTheKindsOfPageThatSitBesideTheBead()
    {
        APageNamed("question-b-7.html", "<p>Q</p>");
        APageNamed("gate-b-7.html", "<p>G</p>");
        APageNamed("question-b-8.html", "<p>Another bead</p>");

        Assert.Equal(
            [JidokaPageKind.Question, JidokaPageKind.Gate],
            pages.KindsBeside(new BeadAddress(project, "b-7")));
    }

    [Theory]
    [InlineData("../b-7")]
    [InlineData("..")]
    [InlineData("a/b")]
    [InlineData("a\\b")]
    [InlineData("")]
    public void ReadsNoFileOutsideTheFolderForAnIdThatIsNotAFileName(string id)
    {
        APageNamed("question-.html", "<p>Empty id</p>");
        APageNamed("question-...html", "<p>Dots</p>");
        File.WriteAllText(Path.Combine(home, "pages", "question-b-7.html"), "<p>Out of reach</p>");

        Assert.Null(pages.Read(JidokaPageKind.Question, new BeadAddress(project, id)));
        Assert.Empty(pages.KindsBeside(new BeadAddress(project, id)));
    }

    [Theory]
    [InlineData("question", JidokaPageKind.Question)]
    [InlineData("gate", JidokaPageKind.Gate)]
    [InlineData("handoff", JidokaPageKind.Handoff)]
    [InlineData("spec-approval", JidokaPageKind.SpecApproval)]
    public void NamesEachKindByTheWordThatItsFileStartsWith(string word, JidokaPageKind kind)
    {
        Assert.True(JidokaPageKinds.TryFrom(word, out var found));
        Assert.Equal(kind, found);
        Assert.Equal(word, kind.Word());
    }

    [Fact]
    public void KnowsNoKindForAWordThatNoScriptWrites()
    {
        Assert.False(JidokaPageKinds.TryFrom("report", out _));
    }

    [Fact]
    public void LocatesTheHomeFromTheEnvironmentBeforeTheFolderOfTheUser()
    {
        Assert.Equal("/elsewhere", JidokaHome.Locate("/elsewhere", "/Users/jeff").Root);
        Assert.Equal(Path.Combine("/Users/jeff", ".jidoka"), JidokaHome.Locate(null, "/Users/jeff").Root);
        Assert.Equal(Path.Combine("/Users/jeff", ".jidoka"), JidokaHome.Locate("  ", "/Users/jeff").Root);
    }

    [Fact]
    public void NamesEachFileAndFolderUnderTheRootOfTheHome()
    {
        var jidokaHome = new JidokaHome("/h");

        Assert.Equal(
            [
                Path.Combine("/h", "settings.json"),
                Path.Combine("/h", "plugins"),
                Path.Combine("/h", "repos"),
                Path.Combine("/h", "pages"),
                Path.Combine("/h", "heartbeat"),
                Path.Combine("/h", "ledger.sqlite"),
            ],
            [
                jidokaHome.SettingsFile,
                jidokaHome.PluginsFolder,
                jidokaHome.ReposFolder,
                jidokaHome.PagesFolder,
                jidokaHome.HeartbeatFolder,
                jidokaHome.LedgerFile,
            ]);
    }

    public void Dispose() => directory.Dispose();

    private void APageNamed(string file, string html)
    {
        var folder = Directory.CreateDirectory(Path.Combine(home, "pages", project.DirectoryName)).FullName;
        File.WriteAllText(Path.Combine(folder, file), html);
    }
}
