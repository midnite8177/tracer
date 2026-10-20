Bare-name Skill calls are left alone, because they resolve inside the
plugin.

<!-- seed -->
**P8 · every skill** — where a body says "tell the user to run
`/setup-matt-pocock-skills`", it says `/tracer:adopt` instead. Where a
body invokes another skill by bare name through the Skill tool, leave it:
bare names resolve inside the plugin. If a bare-name call is ever found
to resolve to the wrong plugin, qualify it as `tracer:<name>` and note it
in the report.

---

