---
name: setup
description: Propose this machine's routes, the default budget, the reserves and the lap limit from what is installed here, and write them once you confirm.
disable-model-invocation: true
argument-hint: "[the route, budget or reserve to change]"
---

The setup script is
`sh "<skill folder>/../../bin/jidoka-run" "<skill folder>/../../scripts/setup.py"`,
where the skill folder is the directory that holds this SKILL.md. It reads
and writes the machine settings in `~/.jidoka`, so it runs from any folder.

1. **Look.** Run `setup.py propose`. It prints the harnesses it found on the
   PATH, how each account bills, the proposed routes, the default budget,
   the reserves and what the settings hold now. It writes nothing.
2. **Show.** Tell the human, in plain words, what it found and what it
   proposes:
   - a route for each tier. When `codex` is not on the PATH, the second
     tier is proposed on native Opus, which is claude at its Opus model.
   - the default budget, in dollars at list price. It is lower for an
     account that bills by API key, where the dollars are real.
   - the reserve of the claude account, which is the share of its usage window the
     factory leaves unused. The factory reads the usage of the claude account
     alone, so no other account gets a reserve, and a claude account on an API
     key has no window and no reserve.
   - the lap limit, which is the most open laps the machine allows. It caps every
     epic's laps, and the laps of all the running epics together. It is 4
     unless the settings hold another. A repo's own lap limit and an epic's
     rule can only lower it for them.
   - what the settings hold now, where it differs from the proposal.
   Say that a route that fails reruns its stage once on the native route.
3. **Ask.** Ask whether to write the proposal as it is, or with changes.
   Take the human's changes into the proposal's `routes`, `budget`,
   `reserves` and `lap_limit`. Write nothing yet. When the human declines, stop here; the
   settings are as they were.
4. **Write.** Only after the human said yes, pipe the confirmed proposal to
   `setup.py write --confirmed` on stdin. It checks all four parts before
   it writes any, and keeps every other machine setting. When it refuses,
   show its message, fix the proposal with the human and run it again.
5. **Report.** Say which settings were written.
