# tracer-seed

The sources of the tracer seed. The seed is
[`docs/seeds/tracer/tracer.md`](../../docs/seeds/tracer/tracer.md), one
Markdown file that `/tracer:adopt` reads to install tracer into a repo.
`build.py` generates it, so edit the sources here and build. See
[ADR 0001](docs/adr/0001-the-seed-is-generated-from-sources.md).

## What you need

Python 3.8 or newer. There are no packages to install.

## Build and test

```bash
python3 projects/tracer-seed/build.py           # write the seed
python3 projects/tracer-seed/build.py --check   # fail if the committed seed is stale
python3 -m unittest discover -s projects/tracer-seed/tests
```

## Where things are

| Path | What it holds |
|---|---|
| `seed.json` | The revision, its date, the upstream pin, the `bd` version, the output path, and the fragments in seed order |
| `src/fragments/` | The seed's prose, one file per block, patch or skill section |
| `src/installed/` | Files the seed carries verbatim and adopt writes out: `docs/agents/` docs, plugin skills and agents, scripts, the status line |
| `docs/design.md` | Why tracer exists and the principles behind its mechanics |
| `docs/implement-run.md` | How a bead moves through `implement` |
| `docs/adr/` | Decisions about the seed |

`src/installed/plugin/` maps to `.claude/skills/tracer/` in an adopted
repo, `src/installed/docs/agents/` to `docs/agents/`, and
`src/installed/statusline.py` to `.claude/statusline.py`.

## How a fragment works

A fragment can open with maintainer notes: why the section has its shape,
and what was tried and reversed. A line reading `<!-- seed -->` ends the
notes, and the build drops everything above it. A fragment with no such
line reaches the seed whole.

A line `{{include <path>}}` is replaced by the file at that path under
`src/`, byte for byte. The fence around it stays in the fragment.

`{{revision}}`, `{{date}}`, `{{upstream_pin}}` and `{{bd_version}}` take
their values from `seed.json`; `{{plugin_version}}` is the pin without its
`v`, then `+tracer.` and the revision. The changelog is history and keeps
literal values.

The build stops when a fragment on disk is not in `seed.json`, when an
installed file is not included by any fragment, when an include names a
missing file, or when the first changelog entry is not the revision in
`seed.json`.

## Releasing a revision

1. Edit the fragments and installed files.
2. Raise `revision` and set `date` in `seed.json`.
3. Add the new entry at the top of `src/fragments/changelog.md`.
4. Run `build.py`, run the tests, and read the diff of the generated seed.
5. Commit the sources and the generated seed together.

To take an upstream update, change `upstream_pin` and re-check the
patches in `src/fragments/block3/` against the new upstream text.
