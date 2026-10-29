using JidokaUi.Core.Boards;
using JidokaUi.Core.Factory;

namespace JidokaUi.Core.Jidoka;

/// <summary>
/// Which of jidoka's parts a bead carries, and whether each has moved on. A page asks here and
/// does not work out the question itself, so the detail page, the needs-you view and a served page
/// agree about a bead.
/// </summary>
/// <param name="Question">The question that waits for an answer on this bead, or null when none does.</param>
/// <param name="WaitsAtTheGate">True while this bead is an epic that waits on the human's decision at the acceptance gate.</param>
/// <param name="TakesRules">True when this bead is an open epic that carries the factory label.</param>
/// <param name="QuestionMovedOn">True when no question waits on this bead any more, or the bead is closed.</param>
public sealed record JidokaParts(BeadQuestion? Question, bool WaitsAtTheGate, bool TakesRules, bool QuestionMovedOn)
{
    /// <summary>True when the epic no longer waits at the gate, because a decision landed or it closed.</summary>
    public bool GateMovedOn => !WaitsAtTheGate;

    /// <summary>The parts that this bead carries.</summary>
    public static JidokaParts Of(Bead bead)
    {
        var question = bead.QuestionToAnswer;
        return new JidokaParts(
            question,
            FactoryEpic.WaitsAtTheGate(bead),
            FactoryEpic.TakesRules(bead),
            question is null || bead.IsClosed);
    }
}
