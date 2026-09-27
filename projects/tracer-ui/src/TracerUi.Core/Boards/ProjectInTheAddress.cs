using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// What the query of an address says about the project of its page. None and NoPath are separate
/// cases. A page may give the tab's project to an address that names none, and never to an address
/// whose project it cannot read.
/// </summary>
public abstract record ProjectInTheAddress
{
    /// <summary>The name that the project carries in the query of every address that names one.</summary>
    public const string QueryName = "project";

    private ProjectInTheAddress()
    {
    }

    /// <summary>
    /// Reads the project value of the query of this address. An empty or missing value is None, and
    /// text that is no absolute path is NoPath.
    /// </summary>
    public static ProjectInTheAddress Of(string address)
    {
        var text = AddressQuery.Of(address).GetValueOrDefault(QueryName, string.Empty);
        if (text.Length == 0)
        {
            return new None();
        }

        return ProjectPath.TryFromAbsolute(text, out var project)
            ? new Named(project)
            : new NoPath(text);
    }

    /// <summary>The query has no project, or a project with no value.</summary>
    public sealed record None : ProjectInTheAddress;

    /// <summary>The query names an absolute path that a project path accepts.</summary>
    public sealed record Named(ProjectPath Project) : ProjectInTheAddress;

    /// <summary>The query carries this text as its project, and the text names no path that the app accepts as a project.</summary>
    public sealed record NoPath(string Text) : ProjectInTheAddress;
}
