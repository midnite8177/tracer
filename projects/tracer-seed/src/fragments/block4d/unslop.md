**Tried and reversed.** `unslop` as a user-invoked skill never fired. See
[ADR 0005](../../../docs/adr/0005-unslop-is-called-by-name.md).

<!-- seed -->
### `unslop`

Source: `https://github.com/cursor/plugins`, `pstack/skills/unslop/SKILL.md`,
MIT (Lauren Tan), commit `93b00b8` (2026-09-04). Written to
`.claude/skills/tracer/skills/unslop/SKILL.md`. **The body is verbatim;
the frontmatter is not.** Upstream ships `disable-model-invocation: true`
with a description reading "Must always apply", which contradict each
other: the flag removes the skill's name and description from what the
model can see, so nothing can apply it unless a human types it. In
pstack, `poteto-mode` calls it by name, so the flag is harmless there.
Tracer has no such caller, so the flag is dropped and the description is
rewritten to be model-facing. Everything below the frontmatter is
upstream's text unchanged.

How it applies in tracer: `implement`, `to-spec` and `research` invoke
it by name before writing prose a human reads (P1, P3, P5), and Block 1
carries a one-line pointer to the file for everything else. A human can
still type `/tracer:unslop` on any text.

Precedence: a host output style (a Claude Code output style, or a style
the user set for the session) and a project style guide win where they
conflict with `unslop`; `unslop` applies where they are silent. The
known conflict is ASD-STE100 Simplified Technical English, which bans
contractions and variation where `unslop` asks for rhythm and voice.

```markdown
{{include installed/plugin/skills/unslop/SKILL.md}}
```

