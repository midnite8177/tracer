namespace JidokaUi.Core.Jidoka;

/// <summary>One assumption that the gate comment numbers, and the bead whose worker recorded it.</summary>
/// <param name="Number">The number that the gate script takes to mark the assumption wrong.</param>
/// <param name="Bead">The id of the bead that recorded it.</param>
/// <param name="Title">The title of that bead.</param>
/// <param name="Text">The assumption, in the worker's words.</param>
public sealed record GateAssumption(int Number, string Bead, string Title, string Text);

/// <summary>A test that the test cleanup removed from the epic branch, and what covers its behavior.</summary>
/// <param name="Test">The name of the test, which the gate script takes to restore it.</param>
/// <param name="File">The file the test was removed from.</param>
/// <param name="CoveredBy">The kept test or acceptance spec that covers the same behavior.</param>
public sealed record RemovedTest(string Test, string File, string CoveredBy);

/// <summary>An open bead outside the epic that a lap or a pass found while it worked on the epic.</summary>
/// <param name="Bead">The id of the bead.</param>
/// <param name="Title">The title of the bead.</param>
/// <param name="FoundIn">The id of the epic or task it was found in.</param>
public sealed record FoundOutsideTheEpic(string Bead, string Title, string FoundIn);

/// <summary>
/// What the small decisions of the acceptance gate name: the numbered assumptions that Wrong takes,
/// the removed tests that Restore takes, and the beads found outside the epic that Keep and Close
/// take. The gate script lists them, because it numbers the assumptions and finds the other two.
/// </summary>
public sealed record GateItems(
    IReadOnlyList<GateAssumption> Assumptions,
    IReadOnlyList<RemovedTest> RemovedTests,
    IReadOnlyList<FoundOutsideTheEpic> FoundOutside);
