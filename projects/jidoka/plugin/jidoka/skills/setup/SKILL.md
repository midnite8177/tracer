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

1. **Look.** Under T3 (the `T3CODE_CLI_PATH` variable is set), call the
   `orchestrator_capabilities` tool with no arguments and save what it
   prints to a file in a scratch folder. Run `setup.py propose`, and under
   T3 add `--t3-catalog <that file>`. Outside T3, pass no catalog. It prints
   the harnesses it found on the PATH, how each account bills, the proposed
   routes, the default budget, the reserves and what the settings hold now.
   It writes nothing.
2. **Show.** Tell the human, in plain words, what it found and what it
   proposes:
   - a route for each tier. Under T3, when the catalog has a Codex
     provider that can run a child task, the second tier is proposed on t3
     Codex, on model gpt-6.1-sol at high effort when the catalog offers
     them, else on a model and effort it does offer. A t3 route needs a
     provider, a model and an effort, and no tier whose stages write may
     take it, as none may take codex. The one exception is the local tier,
     which runs the tidy alone. The human can choose a t3 route there on an
     OpenCode provider of the catalog, written with `"driver": "opencode"`
     beside its provider, model and effort. Setup never proposes it. It
     accepts it for the local tier alone, because the child runs in T3's
     auto-accept-edits mode, where a shell command waits for an approval
     no one gives, and refuses it for any tier that writes more than the
     tidy. Without a catalog, and when `codex` is not on the PATH, the
     second tier is proposed on native Opus, which is claude at its Opus
     model.
   - under an Antigravity host (the proposal's `host` says `antigravity`),
     the routes are the Antigravity table, which is kept apart from Claude
     Code's. Light and local run on Gemini 4 Hydrogen at medium thought,
     standard on Neon at high, and deep on Carbon when the catalog lists it,
     else on Neon at xhigh. Each is a t3 route with the driver `antigravity`,
     the catalog's model id and its thought level as the effort, and the
     catalog's Claude models are never proposed. The second tier is the same
     codex route as on Claude Code, else the deep route. A tier whose model
     the catalog lacks is left out. Tell the human that every jidoka session
     on Antigravity runs in T3's Full access mode, set before its first
     message: in any other mode Antigravity asks before each read of
     jidoka's files in the jidoka home, and the factory refuses to start.
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
   - the proposal's `t3_token`, when `t3` is found: a read-only token for
     T3's local server, which lets jidoka read whether the Antigravity
     account is signed in. It is issued with `t3 auth session issue --scope
     orchestration:read --label jidoka` and a long TTL, and saved in
     jidoka's home in a file only the user can read. Say that the scope is
     the narrowest that serves the status, and that it can also read every
     thread in T3. Say that jidoka never touches the Google login, and that
     nothing is issued until the human says yes. When `recorded` is true, a
     token is saved already, and issuing replaces it.
   Say that a route that fails reruns its stage once on the native route.
3. **Ask.** Ask whether to write the proposal as it is, or with changes.
   Take the human's changes into the proposal's `routes`, `budget`,
   `reserves` and `lap_limit`. Write nothing yet. When the human declines, stop here; the
   settings are as they were.
4. **Write.** Only after the human said yes, pipe the confirmed proposal to
   `setup.py write --confirmed` on stdin. It checks all four parts before
   it writes any, and keeps every other machine setting. It touches
   nothing in OpenCode's config. When it refuses,
   show its message, fix the proposal with the human and run it again.
   Run `setup.py issue-token --confirmed` only when the human said yes to
   the token, and never otherwise. It prints the file's path and not the
   token; never print, quote or log the token yourself.
5. **Report.** Say which settings were written, and whether a token was
   saved. After a token was saved, run `provider_status.py antigravity` (the
   same launcher, the script beside `setup.py`) and tell the human what it
   prints: whether the Antigravity account is signed in, or that T3 gave no
   status and why.
