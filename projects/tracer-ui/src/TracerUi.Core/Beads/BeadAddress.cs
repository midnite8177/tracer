using TracerUi.Core.Projects;

namespace TracerUi.Core.Beads;

/// <summary>
/// The project that holds a bead, together with the id of the bead. Every read and every write of
/// one bead names it, because an id alone means nothing outside the project that holds it.
/// </summary>
public sealed record BeadAddress(ProjectPath Project, string Id);
