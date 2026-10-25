---
name: spec-check
description: "Judge whether a bead's diff does what the bead says, and nothing more, and end with one outcome from a fixed set: pass, send back with findings, or cannot judge. Each finding names a file and line and says whether it is missing work or extra work. Use when a bead's diff since a fixed point needs its Spec check."
license: MIT
argument-hint: "<bead-id> [fixed point]"
metadata:
  upstream: "https://github.com/mattpocock/skills#skills/engineering/code-review"
---

The Spec check holds one bead's diff to the bead. It asks whether the
diff does everything the bead says, and whether it does anything the
bead did not ask for. Nothing else. It runs as a stage worker, so it
works alone from start to finish. It reads files, runs `git`, and
reads the tracker with `bd show`. It writes nothing: no code edits, no
tracker changes, no subagents, no questions to the human. When it
cannot go on, it ends with `cannot judge` and a reason.

`$ARGUMENTS` holds the bead id and, optionally, a fixed point. A person
types `/jidoka:spec-check <bead-id> [fixed point]`; a host passes the
same two arguments.

**1. Pin the fixed point.** Take the commit, branch or tag passed as the
second argument. Without one, take the SHA in the bead's
`implement started at <sha>` comment (`bd show <bead-id>`). Never infer
one from `main`, `HEAD~1`, the last commit or the conversation. Check it
with `git rev-parse`, list `git log <fixed-point>..HEAD --oneline`, and
read the diff once with `git diff <fixed-point>...HEAD` (three dots, so
the diff runs from the merge base). Uncommitted changes are outside the
range. The step is done when the diff is in hand. End with `cannot judge`
when no fixed point resolves, when the diff is empty, or when the commits
are plainly not this bead's work.

**2. Read the repo's rules.** Before the bead, and before jidoka's own
rules, read what the repo says about how work is done: the house rules in
`AGENTS.md` and `CLAUDE.md` and the files they import,
`CODING_STANDARDS.md` or `CONTRIBUTING.md` when present, the
`GLOSSARY.md` of the project the diff touches, and the ADRs under
`docs/adr/` for that area. They decide what the bead's words mean in this
repo. The session opened with the rule conflicts onboarding recorded,
under "This repo's rules win over jidoka's where they conflict"; where
one is recorded, the repo's rule wins, and work that keeps it is neither
missing nor extra. A rule that every change carries a test makes a
missing test missing work, and a glossary term names exactly the thing
the bead asked for. The style of the code and its comments belong to
other stages; leave them alone.

**3. Read the bead.** `bd show <bead-id>`, and the description of its
parent epic for context. The spec is the bead's What, Demo, Seams and
acceptance criteria, amended by any later comment on the bead that
changes them. A `research brief:` comment's "Files to change" is a
checklist: a listed file the diff leaves alone is worth a look, and a
finding only when a line of the bead needs that file. End with
`cannot judge` when the bead has no description.

**4. Judge.** Walk every line of the spec against the diff, then every
hunk of the diff against the spec. Read the code around a hunk when the
hunk alone cannot answer. The step is done when each spec line is met or
has a finding, and each hunk is asked for or has a finding.

- **Missing.** A spec line the diff does not meet: absent, partial, or
  built so that it does not do what the line says. A requirement built
  wrong is missing, because the requirement is not met. The finding
  names the file and line where the work belongs: the nearest place in
  the diff, or the file the bead names.
- **Extra.** Anything the diff adds or changes that no spec line asks
  for: a flag, an option, a new behavior, a refactor of code the bead
  does not touch. The finding names the file and line in the diff.

Some changes are neither missing nor extra, because the bead's own work
needs them. These are a test of the asked behavior, an import, the
wiring that reaches the new code, a README or glossary line describing
the new thing, and whatever the repo's rules require of every change.
Each finding quotes the spec line it rests on; an extra finding quotes
the spec line nearest to it, or says none.

**5. Report.** Write the findings for a person first, grouped by file,
each with its kind, file and line, the quoted spec line, and one line on
what the diff does. Then end the reply with the outcome block.

## The outcome block

The last thing in the reply is one fenced `json` block, and nothing
follows it. The manager, or the agent at the bench, reads only this
block.

```json
{
  "outcome": "send back",
  "findings": [
    {
      "kind": "extra",
      "file": "src/cli.py",
      "line": 42,
      "bead": "none",
      "note": "adds a --verbose flag the bead does not ask for"
    }
  ]
}
```

- `outcome` is one of `pass`, `send back`, `cannot judge`.
- `pass` has an empty `findings` list. `send back` has at least one
  finding. A diff that does its bead's job, and only that, passes.
- Each finding has five fields. `kind` is `missing` or `extra`. `file`
  is a path from the repo root. `line` is a 1-based line number in that
  file at `HEAD`. `bead` is the quoted spec line, or `none`. `note` is
  one line.
- `cannot judge` has an empty `findings` list and a `reason` field of
  one line. `reason` appears with no other outcome.
