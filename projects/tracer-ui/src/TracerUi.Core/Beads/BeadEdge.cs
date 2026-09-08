namespace TracerUi.Core.Beads;

/// <summary>One dependency edge of a bead, as bd printed it.</summary>
/// <param name="Type">What the edge means, for example "blocks" or "parent-child".</param>
/// <param name="TargetId">The bead at the other end of the edge.</param>
public sealed record BeadEdge(string Type, string TargetId);
