using JidokaUi.Core.Boards;

namespace JidokaUi.Core.Projects;

/// <summary>
/// A board filter that the person named and kept. It belongs to the one project that the person
/// saved it in, because an epic id and a label mean nothing in another project.
/// </summary>
public sealed record SavedFilter(ProjectPath Project, string Name, BoardFilter Filter);
