# Context map

This repository holds one context per project. Each context owns its own
vocabulary, and the same word can mean two different things in two of
them.

## Contexts

- [jidoka-ui](projects/jidoka-ui/GLOSSARY.md) — a local web UI for the
  browse and triage of beads issues.
- [tracer-seed](projects/tracer-seed/GLOSSARY.md) — the sources and the
  build of the tracer seed.
- [jidoka](projects/jidoka/GLOSSARY.md) — the tool that replaces tracer:
  planning with the human, the factory, and acceptance.

## Relationships

- **jidoka and jidoka-ui**: an epic in jidoka-ui is any bead that holds
  beads; an epic in jidoka holds only tasks. jidoka-ui avoids "task" as a
  word for a bead, while in jidoka a task is a bead inside an epic. A page
  in jidoka is a file it writes for a bead; jidoka-ui calls it a jidoka
  page, because jidoka-ui's own screens are pages too.

## Decisions

Decisions about the workspace are in [docs/adr/](docs/adr/). Decisions
about a project are in that project's own `docs/adr/`.
