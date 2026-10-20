Upstream `pr` copies this skill's visual menu; `show-me` is the original,
for use in conversation.

<!-- seed -->
### `show-me`

Source: `https://github.com/humanlayer/skills`,
`plugins/show-me/skills/show-me/SKILL.md` (MIT, HumanLayer; Dex Horthy).
Written to `.claude/skills/tracer/skills/show-me/SKILL.md`. Upstream
`pr` copies this skill's menu of visuals into its Summary section and
credits it; this is the original, for use in conversation: "draw me the
call tree", "show me what changes". The body is verbatim except the
last bullet's open command, which upstream gives as macOS `open`; here
it names the opener per platform. It keeps `disable-model-invocation`
(a picture is the human's request). The fence is four backticks because
the body contains three-backtick blocks; write the file with the inner
fences as three.

````markdown
{{include installed/plugin/skills/show-me/SKILL.md}}
````

