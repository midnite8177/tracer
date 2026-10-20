### `show-me-your-work`

Source: `https://github.com/cursor/plugins`, `pstack/skills/show-me-your-work/`,
same license and commit. Written to
`.claude/skills/tracer/skills/show-me-your-work/SKILL.md`, with
`scripts/log.py` (a portable port of upstream's `log.sh`, below) and
`references/decision-log-template.tsv` (one line, the six column
names `ts phase decision why evidence result` separated by tab
characters, exactly what `log.sh` writes on first use). Deltas from upstream: the
log lives at `.audit/<slug>.tsv` and is excluded from git; the
principle-skill reference becomes its sentence; the transcript audit
names Claude Code's transcript location instead of Cursor's; the
cross-model review says what to do when no second model family is
available (say so, never invent a reviewer); `scripts/log.sh` becomes
`scripts/log.py` so it runs on Windows without bash; and the description says
when tracer uses it (long wayfinder efforts, anything the human reviews
after stepping away). It keeps `disable-model-invocation` because
starting a trail is the human's call.

````markdown
{{include installed/plugin/skills/show-me-your-work/SKILL.md}}
````

`scripts/log.py`, a line-for-line port of upstream's `log.sh` (same
columns, same cleaning, same header on first use), tested on the same
inputs:

```python
{{include installed/plugin/skills/show-me-your-work/scripts/log.py}}
```

