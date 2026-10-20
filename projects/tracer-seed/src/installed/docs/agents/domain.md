# Domain docs

Before exploring the codebase, read `GLOSSARY.md` at the root (or
`GLOSSARY-MAP.md` and then each relevant context's `GLOSSARY.md`), and the
ADRs under `docs/adr/` for the area you are touching. If any of these do
not exist, proceed silently; `domain-modeling` creates them lazily.

Use the glossary's vocabulary in bead titles, plan steps, test names and
code. Do not drift to synonyms the glossary marks *Avoid*. If a change
would contradict an ADR, say so explicitly ("contradicts ADR-0007 because
…, worth reopening because …") rather than working around it.
