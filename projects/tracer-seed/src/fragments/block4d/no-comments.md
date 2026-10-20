### `no-comments`

Source: `https://github.com/cursor/plugins`, `pstack/skills/no-comments/SKILL.md`,
MIT (Lauren Tan), commit `93b00b8` (2026-09-04). Written to
`.claude/skills/tracer/skills/no-comments/SKILL.md`. Deltas from
upstream, all forced by skills tracer does not carry: the subagent is
named `tracer:comment-sicko`; `/how` and `/why` become "read the symbol's
callers and its git history"; `/architect` becomes the Skill tool with
"codebase-design"; the two principle-skill references become the one
sentence they stand for; "sketch out-of-scope work" and "report open"
become "file a bead" per the discovered-work rule; the unattended
pre-approval clause is dropped, since tracer sessions are attended; the
flag is dropped and the description is model-facing so `implement` can
call it.

```markdown
{{include installed/plugin/skills/no-comments/SKILL.md}}
```

