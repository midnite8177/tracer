---
name: code-review
description: "Review the changes since a fixed point along three lanes, each in its own subagent: Comments (Part 2 of smells.md), Standards (the repo's documented standards plus Part 1 of smells.md), and Spec (does the diff do what the bead or spec asked). Findings are hypotheses with file and line; the skill never edits code. Use when the user wants a branch, a bead's diff, or work since a fixed point reviewed."
license: MIT
metadata:
  upstream: "https://github.com/mattpocock/skills#skills/engineering/code-review"
---

Review `git diff <fixed-point>...HEAD` along three lanes, each run as
its own subagent so a clean lane cannot hide a dirty one. Findings are
hypotheses: every one cites file and line, and the reader checks the
citation. This skill reports; it never edits code.

## Unattended

A caller that says the run is unattended (each lane of the factory's review
stage does) names one lane, a fixed point, a head, a file list and a report
path, and no human is in the loop. Ask nothing. Step 1 takes the caller's
fixed point and head, and the diff is `git diff <fixed-point> <head> --
<files>`; an empty diff is a clean lane, not a stop. Step 2's spec source is
the epic and its tasks, read with `bd show`. Run only the named lane, in this
worker, with no subagent, as step 5 describes it. Give every finding a size
and a confidence:

- **size**: `small` is a few lines in one place; `medium` is one function or
  one file; `large` reshapes a module or spans files, and is a task of its
  own.
- **confidence**: `high`, `medium` or `low`, as in step 6. It is a grade, not
  a question's percent. Mechanical findings are `high`.

Write the lane's findings to the report as a JSON list of `{"file", "line",
"title", "note", "size", "confidence"}`, where `title` is the smell or rule
and `note` says what it looks like here and the fix. Write `[]` when the lane
finds nothing. Change no other file, and end with the count of findings.

The **Design** lane differs. Its `files` are every module the epic touched, and
it reads each one whole, not as a diff, with the code that calls it and the
code it calls where the judgment needs them. Its catalog is Part 3 of
`smells.md`: Ousterhout's red flags, `../codebase-design/SKILL.md`'s terms and
Farley's tells; Parts 1 and 2 belong to the other lanes. Name a finding by the
red flag, term or tell, in the glossary's words. A caller that passes `hints`
gives lizard's list of functions the epic added or grew past the repo's limits.
A hint is a lead: read the function, report a finding only when the design
reason holds, and leave the hint itself out of the report, since the scheduler
lists every hint at the gate. Size a finding `large` when the module's shape
changes. Most of a module's problems predate the epic: report them too, and the
file and line make the finding.

**1. Pin the fixed point.** Resolution order, and nothing else: (1) a
commit, branch or tag the user passed; (2) if the argument is a bead
id, the SHA in that bead's `bench started at <sha>` or `implement
started at <sha>` comment (`bd show <id>`); (3) ask. Never infer one from `main`, `HEAD~1`, the
last commit, or the conversation. Confirm it resolves
(`git rev-parse`), print `git log <fixed-point>..HEAD --oneline`, and
state in one line that these commits are the work under review. If the
diff is empty, or the list holds commits that are plainly not this
work, stop and say so. Uncommitted changes are invisible to a range;
say so if that is why the diff is empty. Capture the diff command
once: `git diff <fixed-point>...HEAD` (three-dot: merge-base).

**2. Identify the spec source.** In order: the bead (`bd show <id>`,
plus its parent epic's description); a path the user passed; a spec
under `docs/` or `specs/` matching the branch or feature; else ask. If
there is none, the Spec lane is skipped and the report says so. If
the bead carries a `research brief:` comment, read it: its "Pattern
to copy" and "Gotchas" are Standards-lane context, and its "Files to
change" is a checklist for the Spec lane (a listed file left
untouched is a question worth asking). Do not research the codebase
beyond the diff and the files the brief names.

**3. Identify the standards sources.** Anything in the repo documenting
how code should be written (`CODING_STANDARDS.md`, `CONTRIBUTING.md`,
the house rules in `AGENTS.md`), plus `smells.md` beside this skill.
Three rules bind the catalog: **the repo overrides** (a documented
repo standard wins; where it endorses something the catalog flags,
suppress the smell); **skip what tooling enforces** (formatter,
analyzer, linter) and name the tool; and **every smell is a labeled
hypothesis** ("possible Feature Envy"), never a hard violation, except
the mechanical ones the catalog's severity section lists, which are
flagged every time.

**4. Scope.** Skip generated code (path convention or header marker)
and list the skipped files. Read enough surrounding code to judge
structure: the whole function for Long Function, the whole class for
Large Class and Feature Envy, callers for Shotgun Surgery and Message
Chains. Sticky Note (TODO, FIXME, HACK, XXX) is reported even in
unchanged lines the diff touches.

**5. Spawn the three lanes in parallel.** Each brief carries the diff
command, the commit list, the relevant catalog part pasted in full
(the subagent has no other access to it), the standards sources, and
this line: "Do not invoke code-review or spawn additional agents:
perform this review directly."

*Comments lane.* Part 2 of `smells.md`. Mechanical pass first, using
the catalog's severity section: Sticky Note, Zombie Code, Ship's Log,
Autograph, Fence Post, Breadcrumb, Costume, Prose Attribute, Price Tag,
Echo. Then a judgment pass on every comment in the diff with its
adjacent code: apply the Deodorant test; check Subtitles, Liar, Ghost
Reference, Gossip, Mumble, Riddle, Encyclopedia, Uniform, Empty Theater
(not in Python), and whether each Amplifier names its failure (one that
does not is a Mumble). Also flag as a hard finding any bead id,
requirement or user-story id (31d, R-918, US-12), date, work history,
or debugging narrative in a comment, log message, docstring, test name,
user-facing string, or commit message in this range: comments describe
the code, not the work or the paperwork. Then note good comments that
are *missing* (a non-obvious constraint, a cost the caller pays, a
load-bearing line with no Amplifier) as "missing", lower confidence.
Language notes decide what each smell looks like in C++, C# and Python;
Python docstrings on private members are never Empty Theater, and
`} // namespace foo` is a Breadcrumb with no exception.

*Standards lane.* The repo's documented standards and house rules,
then Part 1 of `smells.md`, grouped as the catalog groups them
(Bloaters, Change Preventers, Dispensables, Couplers, OO Abusers), with
the language notes. For each smell decide present, absent, or not
judgeable from this diff; report present only. A documented-standard
breach can be hard; a catalog smell is a judgment call unless the
severity section calls it mechanical.

*Spec lane.* Follow steps 3 and 4 of `../spec-check/SKILL.md`, relative
to the folder that holds this SKILL.md: missing work, including work
built wrong, and extra work, each quoting the spec line. Report in
this skill's finding shape, not spec-check's outcome block. Under 400
words.

**6. Aggregate.** Three sections in this order, comment findings first
because they are cheapest to fix: `## Comments`, `## Standards`,
`## Spec`. Present each lane's report verbatim or lightly cleaned; do
**not** merge or rerank across lanes, since a blended verdict lets the
passing lane hide the failing one. Each finding in this shape:

```
**<Smell or rule>** — <file>:<line>
<one line: what it looks like here>
Why: <one line>
Fix: <the refactoring, named as in the catalog>
Confidence: high | medium | low
```

Group by file, then by line. Mechanical findings are always high
confidence. If a lane finds nothing, one line says so. If the diff
produces more than about thirty findings, report the top thirty by
confidence and severity and say how many were cut. End with a count
per smell and one verdict per lane (clean, minor, needs work), never
one verdict across lanes.

Run this in a fresh session when you can: the context that wrote the
code should not review it.
