# Domain docs

Before you explore the code, read `GLOSSARY.md` at the repo root. If the repo
has a `GLOSSARY-MAP.md`, read that first, then the `GLOSSARY.md` of each
context you touch. Then read the ADRs under `docs/adr/` for the area you
change, and under the context's own `docs/adr/`. If none of these exist,
proceed without them.

Use the glossary's words in bead titles, plans, test names and code. Do not
drift to a synonym the glossary lists under Avoid. If a change would
contradict an ADR, say so outright ("contradicts ADR-NNNN because ..., worth
reopening because ...") and do not work around it.

## jidoka's units of work

These hold in any repo jidoka works in.

- **Milestone.** A bead that holds only epics. The factory never takes one.
- **Epic.** A bead that holds only tasks, and the unit the factory takes. It is self-contained. Neither it nor any of its tasks waits on an open bead outside it.
- **Task.** A bead inside an epic that is not itself an epic. Each task carries a Demo line and a Seams line. See the tracker doc.
- **Handoff.** The step in which the human gives an epic to the factory.
- **Discovered work.** A problem found outside the task you are working on. The tracker doc says where it goes.

A repo's own GLOSSARY.md defines the words of its app. These units are
jidoka's, and the four modes are Planning, Factory, Acceptance and Bench.
Planning ships no product code. Bench builds one bead with the human
answering on the spot.
