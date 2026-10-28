"""An epic's budget, the spend that reaches it, and the park that follows.

The scheduler imports it; no command line runs it. The budget is the epic's `budget` factory rule, else the `budget`
of the machine settings in jidoka's home, in dollars at list price. An epic with neither has none and never parks for
spend. The spend is the epic's `spend.dollars` metadata, the running total that ledger.py keeps. The budget is reached
when the spend is equal to it or above.

A reached budget starts no new stage on the epic. The stages already running finish and are reported as always, and
the epic parks, with a comment that names the spend, once none runs. Taking the human label off the epic after
raising its budget lets the factory go on; with the budget still reached the next call parks the epic again.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import park
import prices
import routes
import rules
from commands import metadata_of
from epics import state_of
from pass_support import park_epic

BUDGET_KEY = "budget"
RESUMES_WHEN = "the epic's budget is raised and the human label comes off"


@dataclass(frozen=True)
class Reached:
    """A budget the epic's spend has reached: the spend, and the budget."""
    spent: float
    budget: float

    @property
    def reason(self) -> str:
        """What the epic did, in words that follow its id."""
        return f"reached its budget of ${self.budget:.2f}"

    @property
    def comment(self) -> str:
        return (f"{park.PARKED_PREFIX}the epic spent ${self.spent:.2f} at list price, and its budget is "
                f"${self.budget:.2f}, so no new stage starts and the factory parked it. Raise the budget with "
                "rules.py, then take the human label off to go on.")


def dollars_in(value: object) -> float | None:
    """The value as dollars above zero, or None when it is not a number of them."""
    return float(value) if isinstance(value, (int, float)) and rules.is_dollars(value) else None


def machine_budget(home: Path) -> float | None:
    """The default budget in the machine settings; settings that cannot be read give none, and a line on stderr."""
    return routes.machine_default(home, BUDGET_KEY, "budget", dollars_in)


def budget_of(shown: dict, home: Path) -> float | None:
    """The epic's budget: its own rule, else the machine's default, else None."""
    own = dollars_in(rules.of_epic(shown).settings.get(BUDGET_KEY))
    return own if own is not None else machine_budget(home)


def spent_by(shown: dict) -> float:
    """The epic's running total at list price; zero when the ledger has priced nothing for it."""
    total = rules.decode(metadata_of(shown).get(prices.SPEND_KEY))
    return float(total) if rules.is_number(total) else 0.0


def reached_by(shown: dict, home: Path) -> Reached | None:
    """The reached budget of an epic that runs, or None when it has no budget, has not reached it, or waits on the
    human or the acceptance gate already."""
    state = state_of(shown)
    if state.labeled_for_human or state.at_the_gate:
        return None
    budget = budget_of(shown, home)
    spent = spent_by(shown)
    return Reached(spent, budget) if budget is not None and spent >= budget else None


def park_epic_at(epic: str, reached: Reached, main_tree: Path) -> None:
    """Parks the epic on the human with the comment that names the spend."""
    park_epic(epic, reached.comment, {}, main_tree)
