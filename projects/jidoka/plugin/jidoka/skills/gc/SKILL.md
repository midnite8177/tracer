---
name: gc
description: Pack the repo's beads store so each bd call opens it faster, keeping every bead and every commit. Use when bd calls feel slow.
disable-model-invocation: true
---

The pack script, run from inside any checkout of the repo:
`sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/pack_store.py"`,
where the skill folder is the directory that holds this SKILL.md. It runs
`bd gc --skip-decay --force`, which keeps every bead, and is safe while a
factory works, because bd serializes the calls to the store.

1. **Pack.** Run the script. Exit 0 prints `before` and `after`, the
   store's size in bytes. Exit 1 puts bd's reason on stderr; show it to
   the human verbatim and stop.
2. **Report.** Give the human the store's size before and after in MB,
   and say every bead and every commit is kept.
