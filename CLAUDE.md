# Instructions for AI agents

## Layout

Every project lives in its own directory under `projects/`, with its own
solution file, its own source projects and its own test project. There is
no solution at the root, and no code is shared between projects. See
[ADR 0001](docs/adr/0001-one-directory-per-project.md).

Read [GLOSSARY-MAP.md](GLOSSARY-MAP.md) and then the `GLOSSARY.md` of the
project you touch, before you explore its code. Use the words that the
glossary defines. Read the ADRs under `docs/adr/` and under the project's
own `docs/adr/` for the area you change. If a change contradicts an ADR,
say so; do not work around it.

## Build and test

Each project README holds its own commands.

- jidoka-ui: [projects/jidoka-ui/README.md](projects/jidoka-ui/README.md)
- jidoka: [projects/jidoka/README.md](projects/jidoka/README.md)

A jidoka test that needs beads uses the fake bd: `add_fake_beads` in
`projects/jidoka/tests/jidoka_fixture.py`, with its folder first on the
PATH of every script the test runs, as `test_scheduler.py` does. Each real
`bd` call takes a second or more. Only the tests the jidoka README names
run real `bd`. When a script makes a call the fake does not answer, add the
call to `tests/fake_bd.py` and compare it in `tests/test_fake_bd.py`.

## Conventions

The code keeps these rules. Keep them in new code.

- **Namespaces are file-scoped. Classes are `sealed`.** A value type is a
  `record`.
- **Nullable reference types are on.** Do not use the null-forgiving
  operator. Model the absent value instead.
- **Write fakes by hand.** There is no mock library, and the tests do not
  need one. See `FakeBd` in the jidoka-ui tests.
- **A test name is a sentence about behavior**, such as
  `ReadsTheBeadsThatBdReadyPrintsAsAJsonArray`. It says what the test
  proves, never which task asked for it.
- **A doc comment says what a type is, or why it has its shape.** It never
  describes the work: no dates, no history, no "fixed as part of". The
  same rule applies to code comments and to log messages.
- **Prefer explicit parameters. Avoid default parameter values**, except
  when the API design genuinely calls for one. Never add a default to make
  a signature change easier; let the compiler find every callsite.
