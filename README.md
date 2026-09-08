# tracer

[![build](https://github.com/midnite8177/tracer/actions/workflows/ci.yml/badge.svg)](https://github.com/midnite8177/tracer/actions/workflows/ci.yml)

A workspace of small tools, built one thin demoable slice at a time. Each
slice runs end to end before the next one starts, which is where the name
comes from.

## Layout

Every project lives in its own directory under `projects/`, with its own
solution file, its own source projects and its own test project. There is
no solution at the root. This keeps the projects independent and makes
shared code a deliberate act — see
[ADR 0001](docs/adr/0001-one-directory-per-project.md) for the reason.

## Projects

- **[tracer-ui](projects/tracer-ui/README.md)** — a local web UI for the
  browse and triage of [beads](https://github.com/gastownhall/beads)
  issues. Blazor Server on .NET 10.

## Vocabulary and decisions

[CONTEXT-MAP.md](CONTEXT-MAP.md) points to the glossary of each project.
Decisions about the workspace are in `docs/adr/`. Decisions about a
project are in that project's own `docs/adr/`.

## License

MIT. See [LICENSE](LICENSE).

`docs/seeds/tracer/tracer.md` carries four files from Lauren Tan's pstack,
which is also MIT. [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) holds
that notice and names the one other upstream project the seed installs.
