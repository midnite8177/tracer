Generalized from a per-repo original: no hard-coded reader, labels rather
than assignee values, no repo-specific shell.

<!-- seed -->
## `human-queue`

For the human who takes their decisions in batches. Everything labeled
`human` gets researched in parallel, then presented one decision at a
time in plain language with a recommendation, and each answer is
recorded on its bead before the next question. It plans and records; it
never implements.

````markdown
{{include installed/plugin/skills/human-queue/SKILL.md}}
````

