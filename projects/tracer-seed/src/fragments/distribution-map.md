## Distribution map

Who executes a rule decides where it lives. Everyone → AGENTS.md. One
skill → that skill. Tracker mechanics → `docs/agents/issue-tracker.md`,
read by any skill that touches beads.

| Content | Home | Who pays for it, when |
|---|---|---|
| The loop, discovered work, house rules, memory rules | AGENTS.md | every context, every turn — keep it small |
| How beads express tickets, specs, maps, claims, blocking | `docs/agents/issue-tracker.md` | skills that publish or fetch, on invocation |
| Triage role → label mapping | `docs/agents/triage-labels.md` | `/tracer:triage` only |
| Read `GLOSSARY.md` and ADRs before exploring | `docs/agents/domain.md` | skills that explore the codebase |
| Upstream skills, patched | `.claude/skills/tracer/skills/*` | on invocation |
| Adopt, issues view, budget, human queue | `.claude/skills/tracer/skills/{adopt,issues,budget,human-queue}` | on invocation |
| Carried third-party skills (`unslop`, `no-comments`, `show-me`, `show-me-your-work`) | `.claude/skills/tracer/skills/{unslop,no-comments,show-me,show-me-your-work}` | on invocation |
| Comment-sicko reviewer | `.claude/skills/tracer/agents/comment-sicko.md` | when `no-comments` spawns it |
| Smell catalog (code + comments, C++/C#/Python) | `.claude/skills/tracer/skills/code-review/smells.md` | pasted into review lanes' briefs on invocation |
| Decision trail | `.audit/<slug>.tsv` (uncommitted) | written by the session, read by the human |
| Issues board renderer | `.claude/skills/tracer/skills/issues/issues.py` | outside the model; zero tokens from a terminal |
| Context budget report | `.claude/skills/tracer/skills/budget/budget.py` | outside the model; zero tokens from a terminal |
| Status line | `.claude/settings.local.json` + `.claude/statusline.py` | every turn, outside the model |
| This seed | `docs/tracer.md` | never at runtime |

---

