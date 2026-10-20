`adopt` re-fetches upstream only when the pin changed, and re-applies the
patches and Blocks 1, 2 and 4 every time. It stays model-invokable so
`/tracer:adopt @seed.md` works; see
[ADR 0002](../../../docs/adr/0002-native-skills-stay-model-invokable.md).

<!-- seed -->
## `adopt`

```markdown
{{include installed/plugin/skills/adopt/SKILL.md}}
```

