"""The list prices that the ledger turns token counts into dollars with, and the hand-written table of them.

A price is dollars for a million tokens, one for each kind of token a model's usage counts. A table of prices is keyed
by model id, such as `claude-sonnet-5-5`, because models of one family differ in price and their cache prices follow
no one ratio. A model id with a snapshot date (`-20251001`) or a context suffix (`[1m]`) is priced as the id without
it. A model the table does not list has no price, and `dollars` answers None for it instead of a guess. A cache price
is None when the provider lists none for the model, and tokens of that kind then have no cost either. The cache write
price is the five-minute one, or OpenAI's thirty-minute one. Haiku 5.5 is priced at its rate for prompts up to
100,000 tokens, because sums of tokens over many steps do not say how long any prompt was.

SPEND_KEY is the epic metadata key that holds the running total of the dollars its runs cost; the ledger writes it and
budget.py reads it.

PRICES is the hand-written table. price_pages.py reads the providers' pricing pages into the table the ledger uses,
and PRICES is the fallback for what those pages do not list.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

TOKENS_PER_PRICE = 1_000_000
SPEND_KEY = "spend.dollars"
SNAPSHOT_DATE = re.compile(r"-\d{8}$")
CONTEXT_SUFFIX = re.compile(r"\[[^\]]*\]$")


@dataclass(frozen=True)
class Tokens:
    """The tokens one agent used, by kind."""
    input: int
    output: int
    cache_read: int
    cache_write: int

    def total(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write


@dataclass(frozen=True)
class Price:
    """Dollars for a million tokens of each kind; a cache price the provider does not list is None."""
    input: float
    output: float
    cache_read: float | None
    cache_write: float | None


PRICES: dict[str, Price] = {
    "claude-fable-5-1": Price(input=10.0, output=50.0, cache_read=0.25, cache_write=12.50),
    "claude-fable-5": Price(input=10.0, output=50.0, cache_read=1.0, cache_write=12.50),
    "claude-opus-5-5": Price(input=4.0, output=20.0, cache_read=0.20, cache_write=5.0),
    "claude-opus-5": Price(input=5.0, output=25.0, cache_read=0.50, cache_write=6.25),
    "claude-opus-4-8": Price(input=5.0, output=25.0, cache_read=0.50, cache_write=6.25),
    "claude-opus-4-7": Price(input=5.0, output=25.0, cache_read=0.50, cache_write=6.25),
    "claude-opus-4-6": Price(input=5.0, output=25.0, cache_read=0.50, cache_write=6.25),
    "claude-sonnet-5-5": Price(input=2.0, output=10.0, cache_read=0.10, cache_write=2.50),
    "claude-sonnet-5": Price(input=2.0, output=10.0, cache_read=0.20, cache_write=2.50),
    "claude-sonnet-4-6": Price(input=3.0, output=15.0, cache_read=0.30, cache_write=3.75),
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125),
    "claude-haiku-4-5": Price(input=1.0, output=5.0, cache_read=0.10, cache_write=1.25),
}


def price_of(model: str, table: Mapping[str, Price]) -> Price | None:
    """The price of the model id in the table, or None when the table lists no such model."""
    listed = CONTEXT_SUFFIX.sub("", model.strip().lower())
    return table.get(listed) or table.get(SNAPSHOT_DATE.sub("", listed))


def cost_of(count: int, price: float | None) -> float | None:
    """What `count` tokens cost at the price; none of a kind cost nothing, even with no price."""
    if count == 0:
        return 0.0
    return None if price is None else count * price


def dollars(model: str | None, used: Tokens, table: Mapping[str, Price]) -> float | None:
    """What the tokens cost at the table's prices, rounded to a millionth of a dollar; zero tokens cost nothing
    whatever the model, and tokens of a model or a kind with no price have no cost."""
    if used.total() == 0:
        return 0.0
    price = price_of(model, table) if model else None
    if price is None:
        return None
    costs = [cost_of(used.input, price.input), cost_of(used.output, price.output),
             cost_of(used.cache_read, price.cache_read), cost_of(used.cache_write, price.cache_write)]
    if any(cost is None for cost in costs):
        return None
    return round(sum(cost for cost in costs if cost is not None) / TOKENS_PER_PRICE, 6)
