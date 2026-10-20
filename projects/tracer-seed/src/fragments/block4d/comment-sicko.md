### `comment-sicko` (agent)

Source: `https://github.com/cursor/plugins`, `pstack/agents/comment-sicko.md`,
same license and commit. Written to
`.claude/skills/tracer/agents/comment-sicko.md`; plugin agents are
namespaced, so `no-comments` addresses it as `tracer:comment-sicko`.
Deltas: the name is kebab-case so the harness can address it; the
`/how` and `/why` sentence becomes callers and git history; the
doc-comment exception covers public **and internal** members, with the
house-rule caveat that a summary restating the name is still meat; and
`TODO`, `FIXME` and `HACK` are named as meat, since work belongs in the
tracker.

```markdown
{{include installed/plugin/agents/comment-sicko.md}}
```

