using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

/// <summary>Builds a bead for a test, so that a test states only the fields it cares about.</summary>
public static class ABead
{
    public static Bead Called(string id, string title) =>
        new(id, title, "task", 2, string.Empty, [], string.Empty, BeadProse.None, [], "open", string.Empty);

    public static Bead Epic(string id, string title) => Called(id, title) with { Type = "epic" };

    /// <summary>The same bead, with this description and no Demo line.</summary>
    public static Bead Describing(this Bead bead, string description) =>
        bead with { Prose = bead.Prose with { Description = description } };

    /// <summary>The same bead, with a description whose Demo line says this.</summary>
    public static Bead Demoing(this Bead bead, string demo) => bead.Describing($"## Demo\n\n{demo}\n");
}
