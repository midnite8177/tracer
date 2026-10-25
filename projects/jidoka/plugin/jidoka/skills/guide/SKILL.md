---
name: guide
description: Ask which jidoka skill or flow fits your situation. A router over the skills in this plugin.
disable-model-invocation: true
license: MIT
metadata:
  upstream: "https://github.com/mattpocock/skills#skills/engineering/ask-matt"
  upstream-base: "24fe0ef7737efae15c87225755e9f6f5965e4888"
---

# Guide

You don't remember every skill, so ask. Use `/jidoka:guide` when you need a route.

The skills directory, the parent of the directory that holds this SKILL.md, is the authority on what is installed; the list of skills you were shown omits user-invoked ones, so never tell the user a skill is missing without listing that directory.

A **flow** is a path through the skills. Most paths run along one **main flow**, and two **on-ramps** merge onto it. Everything else is standalone, or a vocabulary layer that runs underneath.

## The main flow: idea → ship

The route most work travels. You have an idea and want it built.

1. **`/jidoka:grill-with-docs`** sharpens the idea by interview. Start here whenever you are **working in a working directory**: it's stateful, retaining what it learns in `GLOSSARY.md` and ADRs. (No working directory? Use `/jidoka:grill-me` instead, covered under Standalone. Both run the same `/jidoka:grilling` primitive; `grill-with-docs` is the one that leaves a paper trail, which makes it the better of the two whenever a repo is there to leave it in.)
2. **Branch: can you settle every question in conversation?** If a question needs a runnable answer (state, business logic, a UI you have to see), detour through **`/jidoka:prototype`** in the same session. It answers the question with throwaway code and folds the validated decision into the real code. It commits the prototype to a throwaway branch out of main, and leaves a pointer to that branch on the bead with the verdict and the question it settled.
3. **Branch: is this a multi-session build?**
   - **Yes** → **`/jidoka:to-spec`** (turn the thread into a spec), then **`/jidoka:to-tickets`** to split it into tracer-bullet tickets, each declaring its **blocking edges**. Then build the tickets with **`/jidoka:bench`**, one ticket per session, **`/clear`ing context between each one**. Tickets are beads under the spec epic with `bd dep` edges; `/jidoka:issues` shows the frontier. Each ticket is self-contained, so the last one's context is disposable.
   - **No** → Write one bead with Demo and Seams lines. Then use **`/jidoka:bench <bead-id>`**. It requires a bead id even for a small job.

   The bench's build worker uses **`/jidoka:tdd`** for test-first work, and **`/jidoka:spec-check`** holds each bead's diff to the bead before you see it. **`/jidoka:code-review`** checks Comments, Standards, and Spec. Use **`/jidoka:tdd`** alone for a test-first change without a full spec. Use **`/jidoka:code-review`** alone to review work against a fixed point.

   When the work goes up as a pull request, **`/jidoka:pr`** shapes the body: the smallest visual that shows the change, before/after evidence that it works, and a one-way or two-way door call. It's model-invoked, so the agent reaches for it whenever it writes a PR.

4. **`/jidoka:retro`** closes the loop. After a build, and especially one that went sideways, it looks back over a session or a whole epic and suggests changes to the agent's **environment**, not the code: navigation pointers, automated checks, the repo's rules files, jidoka's own skills, tooling. Mechanical mistakes become deterministic checks, and judgement calls become rules. A fix to jidoka itself becomes a bead in jidoka's source repo. The next build then starts from a better environment.

### Context hygiene

Keep steps 1–3 in **one unbroken context window** (don't compact or clear until after `/jidoka:to-tickets`) so the grilling, spec, and tickets all build on the same thinking. Each `/jidoka:bench` then starts fresh, working from the ticket. Run `/jidoka:retro` in the session it's looking back on, before you clear; after clearing, point it at that session's log instead.

The limit on this is the **[smart zone](https://www.aihero.dev/ai-coding-dictionary/smart-zone)**: the window (~150k tokens on state-of-the-art models) within which the model still reasons sharply. If a session approaches it before `/jidoka:to-tickets`, don't push on degraded; `/compact` at the nearest phase boundary and carry on (see Phase boundaries).

## On-ramps

A starting situation that generates work, then merges onto the main flow.

- **Bugs and requests piling up** → **`/jidoka:triage`**. It moves issues through triage roles and produces agent-ready issues, which **`/jidoka:bench`** later picks up.

  Triage is only for issues **you didn't create**: bug reports, incoming feature requests, anything that arrives raw. Tickets that `/jidoka:to-tickets` produced are already agent-ready, so **don't triage them**.

- **Something's broken** → **`/jidoka:diagnosing-bugs`**. For the hard ones: the bug that resists a first glance, the intermittent flake, the regression that crept in between two known-good states. It refuses to theorise until it has a **tight feedback loop** (one command that already goes red on *this* bug), then fixes with a regression test. Once the fix is in, run **`/jidoka:retro`** in the same session to ask what would have prevented the bug; where the real finding is that there's no good seam to lock it down, that's a job for **`/jidoka:improve-codebase-architecture`**.

- **A huge, foggy effort: a greenfield project or a huge feature build, too big for one session** → **`/jidoka:wayfinder`**, the most cognitively demanding flow here. When the way from here to the destination isn't visible yet, it charts a **shared map** of **decision tickets** on the issue tracker and resolves them one at a time, producing **decisions, not deliverables**, until the fog is pushed back and the way is clear. Where **`/jidoka:grill-with-docs`** sharpens an idea you can hold in one session, wayfinder is for the idea you can't, and it's slower and denser, so save it for exactly that, never a well-scoped feature.

  When the map clears, **it stops at decisions, it doesn't build**: merge onto the main flow at **`/jidoka:to-spec`**, which collapses the map's linked decisions into a buildable plan, then `/jidoka:to-tickets` and `/jidoka:bench` as usual. Looping the map straight into `/jidoka:bench` skips that collapse and throws the linked detail away, so go straight to `/jidoka:bench` only when the effort turned out genuinely small.

## Quick routes

- "What do I build next?" → `/jidoka:bench <bead-id>` on a ready bead; `/jidoka:issues` shows the frontier and names the bead.
- "What is ready, what is blocked, show me a bead" → `/jidoka:issues`.
- "What is waiting on me, let's decide them" → `/jidoka:issues human`.
- "Record or change this repo's settings: its apps and their test commands" → `/jidoka:onboard`.
- "Where are my context or tokens going?" → `/jidoka:context`.
- "This reads like it was written by an AI, clean it up" → `/jidoka:unslop`.
- "Strip the comment noise from this diff" → `/jidoka:no-comments`.
- "Keep a decision trail I can review when I'm back" → `/jidoka:show-me-your-work`.
- "Draw it, show me the call tree, what changes here" → `/jidoka:show-me`.

## Codebase health

Not feature work, just upkeep.

- **`/jidoka:improve-codebase-architecture`** runs whenever you have a spare moment to keep the codebase good for agents to operate in. It surfaces **deepening opportunities**; picking one _generates an idea_ you can take into the main flow at `/jidoka:grill-with-docs`. It's the survey that finds the candidates; **`/jidoka:codebase-design`** (below) is the bench you design the chosen one on.

## Vocabulary underneath

Two model-invoked references that run *beneath* the other skills, each the single source of truth for its vocabulary. Reach for them directly when the **words**, not the process, are the problem; or let the skills above pull them in.

- **`/jidoka:domain-modeling`**: sharpen the project's *domain* language: challenge a fuzzy term, resolve an overloaded word ("account" doing three jobs), record a hard-to-reverse decision as an ADR. It's the active discipline `/jidoka:grill-with-docs` drives to keep `GLOSSARY.md` a clean glossary.
- **`/jidoka:codebase-design`** is the deep-module vocabulary (module, interface, depth, seam, adapter, leverage, locality) for designing a module's *shape*: a lot of behaviour behind a small interface at a clean seam. `/jidoka:tdd` and `/jidoka:improve-codebase-architecture` both speak it.

## Phase boundaries

A **phase** is a chunk of work inside a session: the grilling, the implementation, the QA. At the **boundary** between two of them you have four options, and picking between them is the fuzziest decision in this whole map:

- **Continue**: stay put. Costs nothing, loses nothing.
- **`/clear`**: empty the window, when nothing here matters to what's next.
- **Subagent**: send a tightly-scoped task to its own window and get a report back.
- **`/compact`** compresses this context and seeds a fresh session with it. The **default**, at the bottom of the tree rather than the first reach.

Read [PHASE-BOUNDARIES.md](PHASE-BOUNDARIES.md) for the ordered tree: the four questions, the reasoning behind each branch, and why the primary-source cost makes **Continue** the one to rule out first. Make the decision **at** a boundary; mid-phase, continue or split the rest into subagents.

## Standalone

Off the main flow entirely.

- **`/jidoka:grill-me`**: the same relentless interview as `/jidoka:grill-with-docs`, but **stateless**: it saves nothing locally and builds no `GLOSSARY.md`. Reach for it when you are **not working in a working directory** (sharpening a plan, a design, a piece of writing, anything with no repo under it). If you are in a working directory, use `/jidoka:grill-with-docs` instead: it runs the same interview and leaves a paper trail, so it is strictly the better one.
- **`/jidoka:grilling`** is the interview primitive itself: rounds, the frontier, facts are the agent's job and decisions are yours. `/jidoka:grill-me` and `/jidoka:grill-with-docs` are the two named ways in, and `/jidoka:triage`, `/jidoka:wayfinder` and `/jidoka:improve-codebase-architecture` all run it internally. Reach for it directly only when you want the interview with no wrapper around it.
- **`/jidoka:prototype`** is a small, throwaway program that answers one design question: does this state model feel right, or what should this UI look like. Throwaway is a constraint on how the code is written, not a promise to destroy it: the answer folds into the real code, and the prototype itself is kept as a **primary source** on a `prototype/<name>` branch out of main, pointed at from the implementation issue. It's the detour in step 2 of the main flow, but reach for it any time a design question is hard to settle on paper.
- **`/jidoka:research`**: delegate reading legwork to a **background agent**: it investigates a question against **primary sources**, then leaves a cited Markdown file in the repo. Keep working while it reads. The file it produces is something to take *into* the main flow at `/jidoka:grill-with-docs`, since research feeds the thinking rather than replacing it.
- **`/jidoka:to-questionnaire`** comes in when the thing blocking you isn't in your head or the codebase but in **someone else's**, and it writes them a questionnaire to fill in. It's the inverse of `/jidoka:grill-me`: instead of interviewing you about the subject, it interviews you about the **send** (who it's going to, what you need back) and aims the questions at the gap. What comes back is material for `/jidoka:grill-with-docs` or `/jidoka:to-spec`.
- **`/jidoka:wizard`** is for the steps only a **human** can take: provisioning infrastructure, setting up credentials or CI secrets, clicking through an unfamiliar third-party dashboard, running a one-off migration or cutover. It generates an interactive bash script that opens each URL, captures each value, and writes it into `.env` and GitHub secrets, so the procedure stops being something you re-explain to an agent every time. Model-invoked, so the agent reaches for it the moment it hits a wall only you can pass. If the agent could just do it itself, it should; this is for where a human is genuinely in the loop.
- **`/jidoka:wait-what`** is the corrective for a message that didn't land. Use it mid-conversation, inside any other skill, and the agent re-pitches what it just said with the context you were missing, in plain English, using the `GLOSSARY.md` vocabulary. It works after the fact; `/jidoka:grill-with-docs` is the upfront cure, because a shared language agreed early is what stops the jargon arriving at all.
- **`/jidoka:teach`**: learn a concept over multiple sessions, using the current directory as a stateful workspace.
- **`/jidoka:writing-for-agents`** is the reference for writing documents agents consume: skills, AGENTS.md, pointed-at docs.

## Precondition

**`/jidoka:onboard`**: run it once per repo, before your first `/jidoka:bench`. It records the repo settings that bench and landing read: each app with its build, run and test commands, and the commands lap workers may run. Rerun it to change them.
