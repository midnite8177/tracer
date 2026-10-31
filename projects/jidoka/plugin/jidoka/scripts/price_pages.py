#!/usr/bin/env python3
"""Reads the list prices from the providers' pricing pages, and keeps them in a cache in jidoka's home.

Anthropic and OpenAI each publish their pricing page as markdown. On Anthropic's page the table under `## Model
pricing` names each model by its display name, such as `Claude Sonnet 5.5`, which is keyed by its model id,
`claude-sonnet-5-5`. It is the name before any note in parentheses, lowercased, with spaces and dots as hyphens. Its
columns are read by header: base input, output, cache hits and the 5m cache write; the 1h write is not priced. A
model with two rows, such as Haiku 5.5 split by prompt length, takes the first. On OpenAI's page the standard tier
is each `### Standard pricing data` section, whose tables name models by id; the batch, flex, fast and ultrafast
sections are other tiers and price nothing. A row split by context length, such as `gpt-5.5 (<272K context
length)`, is keyed by the id before the parenthesis and priced at its short context rates. Its cache write is the
30m one. A `-` is no price, never a free one. A cell's footnote mark (`<sup>3</sup>`) is not part of its number.

The cache is <jidoka-home>/prices.json: {"fetched_at", the second it was fetched, and "prices", each model id's
"input", "output", "cache_read" and "cache_write", in dollars for a million tokens}. A cache older than seven days,
or no cache, makes the next lookup fetch both pages and write a new cache whole. When a fetch or a parse fails, the
cache stays as it was, the lookup prices with it, or with the hand-written table in prices.py when there is none,
and says so on stderr. A cache that cannot be read counts as none. The cache's prices win, and the hand-written
table prices what the pages do not list.

$JIDOKA_PRICE_PAGES, when it names a folder, stands in for the network: the pages are read from
anthropic-pricing.md and openai-pricing.md in it, so a test can serve saved copies.

`list` prints {"fetched_at", the second the prices were fetched, or null for the hand-written table alone,
"prices"}, the table the ledger prices with, fetching first when the cache is stale.

The home is --jidoka-home, else $JIDOKA_HOME, else ~/.jidoka.

Exit codes:
  0  success, whether it priced with fetched, cached or hand-written prices.
  2  a usage error.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import clock
import prices
import settings_reader
import routes
from prices import Price, Tokens

CACHE_FILE = "prices.json"
PAGES_VARIABLE = "JIDOKA_PRICE_PAGES"
MAX_AGE_SECONDS = 7 * 86400
PAGE_TIMEOUT_SECONDS = 5
USER_AGENT = "jidoka"
AMOUNT = re.compile(r"\$\s*(\d+(?:\.\d+)?)")
MARKUP = re.compile(r"<[^>]+>")
SPACES_AND_DOTS = re.compile(r"[\s.]+")


class PageError(Exception):
    """A pricing page that could not be fetched, or that held no price table."""


@dataclass(frozen=True)
class Columns:
    """The headers of the columns that hold one table's standard prices."""
    input: str
    output: str
    cache_read: str
    cache_write: str


@dataclass(frozen=True)
class Page:
    """One provider's pricing page: where it is, the name of its saved copy, and how its prices are read."""
    url: str
    saved_copy: str
    read: Callable[[str], dict[str, Price]]


@dataclass(frozen=True)
class Cache:
    """The prices fetched from the pages, and the second they were fetched."""
    fetched_at: int
    prices: dict[str, Price]


ANTHROPIC_COLUMNS = (Columns("Base input tokens", "Output tokens", "Cache hits and refreshes", "5m cache writes"),)
OPENAI_COLUMNS = (Columns("Short context input", "Short context output", "Short context cached input",
                          "Short context 30m write"),
                  Columns("Input", "Output", "Cached input", "30m write"))


def sections_under(text: str, heading: str) -> list[list[str]]:
    """The lines under each heading line that reads `heading`, each up to the next heading of any level."""
    found: list[list[str]] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("#"):
            inside = line.strip() == heading
            if inside:
                found.append([])
        elif inside:
            found[-1].append(line)
    return found


def cells_of(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def tables_in(lines: list[str]) -> list[list[dict[str, str]]]:
    """Each markdown table in the lines, as its rows keyed by the header's cells."""
    tables: list[list[dict[str, str]]] = []
    block: list[list[str]] = []
    for line in [*lines, ""]:
        if line.lstrip().startswith("|"):
            block.append(cells_of(line))
            continue
        if len(block) > 2:
            header = block[0]
            tables.append([dict(zip(header, row)) for row in block[2:] if len(row) == len(header)])
        block = []
    return tables


def amount_in(cell: str | None) -> float | None:
    """The dollars a price cell starts with, or None for a `-`, an empty cell or no cell."""
    if cell is None:
        return None
    found = AMOUNT.match(MARKUP.sub("", cell).strip())
    return float(found.group(1)) if found else None


def name_in(cell: str) -> str:
    """The model's name in a table's first cell, without the note in parentheses that follows it."""
    return cell.split(" (", 1)[0].strip()


def anthropic_id(cell: str) -> str:
    return SPACES_AND_DOTS.sub("-", name_in(cell).lower())


def openai_id(cell: str) -> str:
    return name_in(cell).lower()


def prices_in(sections: list[list[str]], choices: tuple[Columns, ...],
              id_of: Callable[[str], str]) -> dict[str, Price]:
    """The prices of every table in the sections whose header has the columns of one of the choices, the first row
    of a model winning. A row with no input or output price is left out."""
    found: dict[str, Price] = {}
    for section in sections:
        for rows in tables_in(section):
            if not rows:
                continue
            columns = next((choice for choice in choices if choice.input in rows[0] and choice.output in rows[0]),
                           None)
            if columns is None:
                continue
            for row in rows:
                model = id_of(row.get("Model", ""))
                input_price, output_price = amount_in(row.get(columns.input)), amount_in(row.get(columns.output))
                if not model or model in found or input_price is None or output_price is None:
                    continue
                found[model] = Price(input_price, output_price, amount_in(row.get(columns.cache_read)),
                                     amount_in(row.get(columns.cache_write)))
    return found


def anthropic_prices(text: str) -> dict[str, Price]:
    return prices_in(sections_under(text, "## Model pricing"), ANTHROPIC_COLUMNS, anthropic_id)


def openai_prices(text: str) -> dict[str, Price]:
    return prices_in(sections_under(text, "### Standard pricing data"), OPENAI_COLUMNS, openai_id)


PAGES = (Page("https://platform.claude.com/docs/en/about-claude/pricing.md", "anthropic-pricing.md",
              anthropic_prices),
         Page("https://developers.openai.com/api/docs/pricing.md", "openai-pricing.md", openai_prices))


def location_of(page: Page) -> str:
    """The page's URL, or the file URL of its saved copy when $JIDOKA_PRICE_PAGES names a folder."""
    folder = os.environ.get(PAGES_VARIABLE, "").strip()
    return (Path(folder).resolve() / page.saved_copy).as_uri() if folder else page.url


def fetched(page: Page) -> dict[str, Price]:
    """The page's prices; raises PageError when it cannot be fetched or holds none."""
    location = location_of(page)
    try:
        request = urllib.request.Request(location, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=PAGE_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8")
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise PageError(f"could not fetch {location}: {error}") from error
    found = page.read(text)
    if not found:
        raise PageError(f"{location} holds no price table jidoka can read")
    return found


def price_from(written: object) -> Price | None:
    """The price a cache entry holds, or None when its prices are not numbers."""
    if not isinstance(written, dict):
        return None
    amounts = [written.get(kind) for kind in ("input", "output", "cache_read", "cache_write")]
    if not all(amount is None or (isinstance(amount, (int, float)) and not isinstance(amount, bool))
               for amount in amounts):
        return None
    input_price, output_price, cache_read, cache_write = amounts
    if input_price is None or output_price is None:
        return None
    return Price(float(input_price), float(output_price), None if cache_read is None else float(cache_read),
                 None if cache_write is None else float(cache_write))


def cache_path(home: Path) -> Path:
    return home / CACHE_FILE


def read_cache(home: Path) -> Cache | None:
    """The cache in the home, or None when there is none or it cannot be read."""
    try:
        written = json.loads(cache_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(written, dict):
        return None
    fetched_at, listed = written.get("fetched_at"), written.get("prices")
    if not isinstance(fetched_at, int) or isinstance(fetched_at, bool) or not isinstance(listed, dict):
        return None
    found = {model: price_from(entry) for model, entry in listed.items() if isinstance(model, str)}
    return Cache(fetched_at, {model: found_price for model, found_price in found.items() if found_price is not None})


def write_cache(home: Path, cache: Cache) -> None:
    """Replaces the cache whole, so that a lookup running beside this one never reads half of it."""
    written = {"fetched_at": cache.fetched_at,
               "prices": {model: asdict(price) for model, price in cache.prices.items()}}
    routes.write_in_home(home, CACHE_FILE, json.dumps(written, indent=2) + "\n")


def when(second: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(second))


def current_cache(home: Path) -> Cache | None:
    """The cache, fetched again first when it is older than seven days or missing. A failed fetch keeps the cache
    that was there and says so on stderr."""
    kept = read_cache(home)
    now = clock.now()
    if kept is not None and now - kept.fetched_at <= MAX_AGE_SECONDS:
        return kept
    try:
        fresh = Cache(now, {model: price for page in PAGES for model, price in fetched(page).items()})
    except PageError as error:
        fallback = (f"the prices fetched at {when(kept.fetched_at)}" if kept is not None
                    else "the hand-written table")
        print(f"prices: {error}; pricing with {fallback}", file=sys.stderr)
        return kept
    try:
        write_cache(home, fresh)
    except OSError as error:
        print(f"prices: could not write {cache_path(home)}: {error}", file=sys.stderr)
    return fresh


def list_prices(home: Path) -> tuple[Cache | None, dict[str, Price]]:
    """The cache the prices came from, None when there is none, and the table the ledger prices with."""
    cache = current_cache(home)
    return cache, {**prices.PRICES, **(cache.prices if cache is not None else {})}


def dollars(home: Path, model: str | None, used: Tokens) -> float | None:
    """What the tokens cost at list price. It looks the prices up, which may fetch the pages, only when there are
    tokens of a named model to price."""
    if model is None or used.total() == 0:
        return prices.dollars(model, used, {})
    return prices.dollars(model, used, list_prices(home)[1])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="price_pages.py", description="Print the list prices the ledger prices "
                                                                        "with, fetching the providers' pages first "
                                                                        "when the cache is stale.")
    modes = parser.add_subparsers(dest="mode", required=True)
    listed = modes.add_parser("list", help="print the list prices by model id")
    listed.add_argument("--jidoka-home", help="the folder that holds jidoka's per-machine state")
    args = parser.parse_args(argv)

    cache, table = list_prices(settings_reader.jidoka_home(args.jidoka_home))
    print(json.dumps({"fetched_at": cache.fetched_at if cache is not None else None,
                      "prices": {model: asdict(price) for model, price in sorted(table.items())}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
