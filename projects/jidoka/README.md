# jidoka

The tool that replaces tracer. See [GLOSSARY.md](GLOSSARY.md) for its
words and [docs/adr/](docs/adr/) for its decisions.

## What you need

Python 3.10 or newer, with `git` and `bd` on the PATH. There are no
packages to install.

## Build and test

```bash
python3 projects/jidoka/untracer.py --repo <path>   # backups go to ~/.jidoka; --jidoka-home overrides
python3 -m unittest discover -s projects/jidoka/tests
```

The tests run the script as a process against a temporary git repo, a real
`bd init --stealth` workspace and a temporary jidoka home. Building the
workspace takes a few seconds per test class.

## Where things are

| Path | What it holds |
|---|---|
| `untracer.py` | Takes tracer's files out of one repo, after copying each original to `<jidoka-home>/untracer/` |
| `tests/test_untracer.py` | The untracer tests, at the process seam |
| `tests/tracer_fixture.py` | Builds fixture repos with a tracer install, from the seed sources in this repo's git history |
| `docs/adr/` | Decisions about jidoka |
