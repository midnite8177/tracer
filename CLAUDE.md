# Instructions for AI agents

## Layout

Every project lives in its own directory under `projects/`, with its own
solution file, its own source projects and its own test project. There is
no solution at the root, and no code is shared between projects. See
[ADR 0001](docs/adr/0001-one-directory-per-project.md).

Read [CONTEXT-MAP.md](CONTEXT-MAP.md) and then the `CONTEXT.md` of the
project you touch, before you explore its code. Use the words that the
glossary defines. Read the ADRs under `docs/adr/` and under the project's
own `docs/adr/` for the area you change. If a change contradicts an ADR,
say so; do not work around it.

## Build and test

Each project README holds its own commands.

- tracer-ui: [projects/tracer-ui/README.md](projects/tracer-ui/README.md)

## Conventions

The code keeps these rules. Keep them in new code.

- **Namespaces are file-scoped. Classes are `sealed`.** A value type is a
  `record`.
- **Nullable reference types are on.** Do not use the null-forgiving
  operator. Model the absent value instead.
- **Write fakes by hand.** There is no mock library, and the tests do not
  need one. See `FakeBd` in the tracer-ui tests.
- **A test name is a sentence about behavior**, such as
  `ReadsTheBeadsThatBdReadyPrintsAsAJsonArray`. It says what the test
  proves, never which task asked for it.
- **A doc comment says what a type is, or why it has its shape.** It never
  describes the work: no dates, no history, no "fixed as part of". The
  same rule applies to code comments and to log messages.
- **Prefer explicit parameters. Avoid default parameter values**, except
  when the API design genuinely calls for one. Never add a default to make
  a signature change easier; let the compiler find every callsite.
