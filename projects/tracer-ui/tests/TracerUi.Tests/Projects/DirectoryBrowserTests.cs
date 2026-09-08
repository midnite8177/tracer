using System.Runtime.Versioning;
using TracerUi.Core.Projects;

namespace TracerUi.Tests.Projects;

public class DirectoryBrowserTests
{
    [Fact]
    public void ListsTheSubdirectoriesInNameOrder()
    {
        using var temp = new TempDirectory();
        temp.CreateSubdirectory("zulu");
        temp.CreateSubdirectory("alpha");
        File.WriteAllText(Path.Combine(temp.Path, "a-file.txt"), "not a directory");

        var listing = DirectoryBrowser.Browse(temp.Path);

        Assert.Equal(["alpha", "zulu"], listing.Directories.Select(entry => entry.Name));
    }

    [Fact]
    public void GivesTheParentOfTheDirectory()
    {
        using var temp = new TempDirectory();
        var child = temp.CreateSubdirectory("child");

        var listing = DirectoryBrowser.Browse(child);

        Assert.Equal(temp.Path, listing.ParentPath);
    }

    [Fact]
    public void GivesNoParentAtTheRootOfTheFilesystem()
    {
        var root = Path.GetPathRoot(Path.GetTempPath())!;

        var listing = DirectoryBrowser.Browse(root);

        Assert.Null(listing.ParentPath);
    }

    [Fact]
    public void MarksASubdirectoryThatHoldsABeadsDirectoryAsAProject()
    {
        using var temp = new TempDirectory();
        var repository = temp.CreateSubdirectory("tracer");
        Directory.CreateDirectory(Path.Combine(repository, ".beads"));
        temp.CreateSubdirectory("not-a-project");

        var listing = DirectoryBrowser.Browse(temp.Path);

        Assert.True(listing.Directories.Single(entry => entry.Name == "tracer").IsProject);
        Assert.False(listing.Directories.Single(entry => entry.Name == "not-a-project").IsProject);
    }

    [Fact]
    public void ShowsADirectoryWhoseNameStartsWithADot()
    {
        using var temp = new TempDirectory();
        temp.CreateSubdirectory(".config");
        temp.CreateSubdirectory("visible");

        var listing = DirectoryBrowser.Browse(temp.Path);

        Assert.Equal([".config", "visible"], listing.Directories.Select(entry => entry.Name));
    }

    [WindowsFact]
    public void GivesTheDriveLettersAsRootsOnWindows()
    {
        using var temp = new TempDirectory();

        var listing = DirectoryBrowser.Browse(temp.Path);

        Assert.Contains(Path.GetPathRoot(temp.Path), listing.Roots);
    }

    [UnixFact]
    [UnsupportedOSPlatform("windows")]
    public void GivesASingleRootOnASingleRootedSystem()
    {
        using var temp = new TempDirectory();

        var listing = DirectoryBrowser.Browse(temp.Path);

        Assert.Equal([Path.DirectorySeparatorChar.ToString()], listing.Roots);
    }

    [UnixFact]
    [UnsupportedOSPlatform("windows")]
    public void ShowsAnEmptyListForADirectoryThatThePersonCannotRead()
    {
        using var temp = new TempDirectory();
        var closed = temp.CreateSubdirectory("closed");
        Directory.CreateDirectory(Path.Combine(closed, "child"));
        File.SetUnixFileMode(closed, UnixFileMode.None);

        try
        {
            var listing = DirectoryBrowser.Browse(closed);

            Assert.Empty(listing.Directories);
            Assert.Equal(temp.Path, listing.ParentPath);
        }
        finally
        {
            File.SetUnixFileMode(closed, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }
    }
}
