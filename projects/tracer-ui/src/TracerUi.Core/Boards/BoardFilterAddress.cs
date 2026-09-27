using TracerUi.Core.Projects;

namespace TracerUi.Core.Boards;

/// <summary>
/// The project and the board filter as the address of the board carries them. A part that states
/// nothing appears in no query, so the address that names the project alone is the filter that keeps
/// every live bead of it. This is what makes a filter press a link. The link carries the project and
/// the whole filter, with the one part that the press sets, so the address of the board says what a
/// person is looking at, a second tab shows the same beads, and the Back button of the browser undoes
/// a press.
/// </summary>
public static class BoardFilterAddress
{
    /// <summary>The page that every board address names.</summary>
    public const string Page = "board";

    private const string Status = "status";
    private const string Type = "type";
    private const string Priority = "priority";
    private const string Label = "label";
    private const string Epic = "epic";
    private const string Text = "text";
    private const string NeedsYou = "needs-you";
    private const string NoDemo = "no-demo";
    private const string Deferred = "deferred";
    private const string Closed = "closed";
    private const string True = "true";

    /// <summary>
    /// The address of the board of this project that this filter narrows. The project comes first and
    /// the parts follow one order, so the same filter always gives the same address and two of them
    /// compare as text.
    /// </summary>
    public static string Of(ProjectPath project, BoardFilter filter)
    {
        var parts = new List<string>();
        Add(parts, ProjectInTheAddress.QueryName, project.Value);
        Add(parts, Status, filter.Status);
        Add(parts, Type, filter.Type);
        Add(parts, Priority, filter.Priority);
        Add(parts, Label, filter.Label);
        Add(parts, Epic, filter.Epic);
        Add(parts, Text, filter.Text);
        Add(parts, NeedsYou, filter.RequiresHumanLabel ? True : string.Empty);
        Add(parts, NoDemo, filter.RequiresNoDemoLine ? True : string.Empty);
        Add(parts, Deferred, filter.ShowDeferred ? True : string.Empty);
        Add(parts, Closed, filter.ShowClosed ? True : string.Empty);

        return $"{Page}?{string.Join('&', parts)}";
    }

    /// <summary>
    /// The address of the board of this project with no filter, which shows every live bead of it. A
    /// page with no project to name gives the board page alone.
    /// </summary>
    public static string OfEverythingIn(ProjectPath? project) =>
        project is null ? Page : Of(project, BoardFilter.Everything);

    /// <summary>
    /// The filter that the query of this address states. A name that no part answers to says nothing,
    /// so an address that a person typed by hand narrows the board by the parts that it does name, and
    /// the project is no part of the filter.
    /// </summary>
    public static BoardFilter FilterIn(string address)
    {
        var query = AddressQuery.Of(address);

        return new BoardFilter(
            Status: query.GetValueOrDefault(Status, string.Empty),
            Type: query.GetValueOrDefault(Type),
            Priority: query.GetValueOrDefault(Priority),
            Label: query.GetValueOrDefault(Label),
            Epic: query.GetValueOrDefault(Epic),
            Text: query.GetValueOrDefault(Text, string.Empty),
            RequiresHumanLabel: IsTrue(query, NeedsYou),
            RequiresNoDemoLine: IsTrue(query, NoDemo),
            ShowDeferred: IsTrue(query, Deferred),
            ShowClosed: IsTrue(query, Closed));
    }

    private static void Add(List<string> parts, string name, string? value)
    {
        if (value is { Length: > 0 })
        {
            parts.Add($"{name}={Uri.EscapeDataString(value)}");
        }
    }

    private static bool IsTrue(IReadOnlyDictionary<string, string> query, string name) =>
        string.Equals(query.GetValueOrDefault(name, string.Empty), True, StringComparison.OrdinalIgnoreCase);
}
