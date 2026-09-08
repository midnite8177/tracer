# Seed: `smell-review` skill

Hand this to Claude Code with: "Turn this seed into a skill." It describes what to build, the decisions already made, and what done looks like. It does not contain the skill.

The catalogue it reviews against is `smells.md` (in this folder). Ship that file with the skill, verbatim, as a reference. This seed assumes nothing else: no tracker, no other skills.

## What it is

A code review skill that reads a diff and reports smells from `smells.md`: Fowler's code smells (Part 1) and the comment smells (Part 2). It reports. It never edits code.

Languages: C++, C#, Python. Use the language-notes tables in `smells.md` to decide what a smell looks like in each.

## Decisions already made

**One skill, two lanes.** Not two skills. Code smells and comment smells overlap (Deodorant is Long Function seen from the comment side), and Fowler lists Comments as a code smell. But the lanes run as separate subagents and report separately, so a clean lane cannot hide a dirty one. Dedupe only where two findings share one fix.

**Three SKILL.md files.**
- `smell-review` — the front door. User-invoked only (`disable-model-invocation: true`). Takes a diff range, fans out the two lanes, assembles the report.
- `code-smells` — the code lane. Model-invoked. Holds the reading rules for Part 1. Other skills or agents can use it alone, e.g. during a refactor pass.
- `comment-smells` — the comment lane. Model-invoked. Holds the reading rules and mechanical patterns for Part 2.

The split lets the reusable discipline be reached for on its own while the orchestration only runs when a human asks for it.

**Findings are hypotheses.** Every finding cites file and line. The reader checks the citation. The skill does not fix.

**Repo overrides catalogue.** If the repo documents a standard that contradicts `smells.md`, the repo wins. Skip any smell the repo's tooling already enforces (formatter, analyzer, linter) and say which tool covers it.

**Sticky Note is zero tolerance.** TODO/FIXME/HACK/XXX are always reported, including in unchanged lines the diff touches.

**Amplifier must name its failure.** An "important" comment that does not say what breaks is a Mumble, not an Amplifier.

**Python exceptions.** Empty Theater is not a smell in Python. Docstrings on `_private` members are fine. Echo still applies.

**No namespace exception.** `} // namespace foo` is a Breadcrumb.

## Inputs

- A diff range. Default: merge base with the default branch to `HEAD`. Accept an explicit git range or a list of files.
- Optional: a spec, ticket, or description of intent, for context only. This skill does not check whether the diff did what was asked; that is a different review.

## What each lane does

**Code lane** (`code-smells`):
1. Read the diff plus enough surrounding code to judge structure: the whole function for Long Function, the whole class for Large Class and Feature Envy, callers for Shotgun Surgery and Message Chains.
2. Walk Part 1 of the catalogue. For each smell, decide: present, absent, or not judgeable from this diff.
3. Report present smells only.

**Comment lane** (`comment-smells`):
1. Mechanical pass first: pattern-match Sticky Note, Zombie Code, Ship's Log, Autograph, Fence Post, Breadcrumb, Costume, Prose Attribute, Price Tag, and Echo (summary text ≈ member name). No model judgment needed.
2. Judgment pass: read every comment in the diff with its adjacent code. Apply the Deodorant test. Check Liar, Ghost Reference, Gossip, Mumble, Riddle, Encyclopedia, Uniform, Empty Theater (non-Python), and whether each Amplifier names its failure.
3. Also note good comments that are missing: a non-obvious constraint, a cost the caller pays, a load-bearing line with no Amplifier. Report as "missing" with lower confidence.

## Output

One report, two sections, in this order: Comment lane, Code lane. Comment findings are cheaper to fix; put them first so they get done.

Per finding:

```
**<Smell name>** — <file>:<line>
<one line: what it looks like here>
Why: <one line>
Fix: <the refactoring, named as in the catalogue>
Confidence: high | medium | low
```

Group by file. Within a file, by line. Mechanical findings are always high confidence.

End with a count per smell and a one-line verdict per lane: clean, minor, or needs work. Never blend the two verdicts into one.

If a lane finds nothing, say so in one line. Do not pad.

## Rules for the orchestrator

- Run both lanes in parallel. Two subagents, no more. Subagents do not invoke `smell-review` and do not spawn subagents.
- Recommend running in a fresh session. The context that wrote the code should not review it.
- Uncommitted work is invisible to a git range. Say so if the range is empty.
- If a diff produces more than ~30 findings, report the top 30 by confidence and severity and say how many were cut.
- Skip generated code. Detect by path convention or header marker; list the skipped files.

## Files to ship

```
smell-review/
  SKILL.md                 # orchestrator, user-invoked
  references/smells.md     # the catalogue, verbatim
code-smells/
  SKILL.md                 # code lane reading rules + pointer to Part 1
comment-smells/
  SKILL.md                 # comment lane reading rules + mechanical patterns + pointer to Part 2
```

Mechanical patterns for the comment lane, to start from (extend per language):

| Smell | Pattern (sketch) |
|---|---|
| Sticky Note | `\b(TODO\|FIXME\|HACK\|XXX)\b` inside a comment |
| Zombie Code | Comment lines that parse as code: end in `;`, `{`, or `}`, or start with a keyword (`if`, `for`, `return`, `def`, `class`, `var`, `auto`) |
| Ship's Log | Comment block in the first 30 lines with 2+ dated lines or "changed/added/fixed" lines |
| Autograph | `@author`, `added by`, `written by`, `modified by` in a comment |
| Fence Post | `#region`, `#pragma region`, or a comment line that is mostly `-`, `=`, `/`, `*`, `#` with a short word in the middle |
| Breadcrumb | `}` followed by a comment on the same line; Python: `# end` after a dedent |
| Costume | `<[a-z]+>` tags or Markdown headers `^#{1,3} ` inside a non-docstring comment |
| Prose Attribute | `obsolete`, `deprecated`, `do not use` in a comment on a member with no matching attribute or decorator |
| Price Tag | A numeric literal on a line with a comment that is one or two words (a unit or a name) |
| Echo | Doc summary whose words, stemmed and lowercased, are a subset of the member name split on case or underscore |

## Done looks like

- Running `smell-review` on a diff with one planted example of each of the 20 comment smells reports all 20, correctly named, with correct lines.
- Running it on a diff with a planted Long Function, Feature Envy, Data Clump, and Primitive Obsession reports all four with the right fixes.
- Running it on a clean diff produces a two-line report.
- The Python Empty Theater exception and the C++ namespace non-exception are both exercised.
- Two subagents total. No nesting.
- Report fits on one screen for a typical 200-line diff.

## Writing rules for the SKILL.md files

- Delete anything the model already knows. Do not explain what a code smell is.
- Do not restate the catalogue. Point at it.
- Lead with the action.
- Phrase rules as what to do ("report present smells only"), not what to avoid.
- The document gets shorter as it gets better.
