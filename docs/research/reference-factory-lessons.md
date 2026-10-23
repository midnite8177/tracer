# What the reference factory learned

Research for the wayfinder map "Design new tracer factory workflow". It asks
what Cole Medin's ai-software-factory and its history show about the stages a
lap runs, how holdouts stay hidden, which caps stop a loop, what the manager
does, how parallel laps stay apart, how permissions work unattended, and what
the incident notes say went wrong. Then it asks which of that bears on
jidoka.

## Short answer

The factory went through four designs in seven weeks, and
`docs/incidents.md` records what broke along the way. The current lap is one
run of Archon's `archon-loop` workflow, and it makes one move. A pick agent
chooses an item and a route. A script claims it. A builder works it in the
loop, or `archon-ship` takes it if it is complex. A black-box agent then tests
the running app against the contract and the holdout before it reads any
diff, and a script checks that every line of that report cites evidence
written during the check. A reviewer reads the diff and decides. A script
with no model merges only what the record supports.

Holdouts now live outside the repository and reach only the app check and
the manager. The repo says plainly that a directory named "holdout" is not
privacy. The current design keeps them private by path and by prompt, not by
a sandbox.

The caps are an attempt cap of 3 and a send-back cap of 2 per item. A claim
expires after 6 hours. Agent nodes time out after 45 minutes idle. The
manager has its own limits per pass. At a cap, pick labels the item
`needs-owner` with a question and moves on, so a cap stops one item and not
the factory. The first design also had a watchdog that halted the
whole factory when the sequence of dispatches looked like a loop.

The manager is a second workflow on a slower schedule. It sees across items,
keeps the loop healthy, owns the holdout set, asks the owner questions with a
48-hour default, and logs one metrics line per pass.

Parallel laps claim an item with a GitHub comment, and the oldest claim wins.
Each claim declares the area it will touch, and pick stays clear of claimed
areas. The scheduler lets only one lap choose at a time. The merge gate
refuses any head that does not contain the current default branch.

Permissions went from per-node allow and deny lists, probed in both
directions, to Archon running Claude Code in `bypassPermissions`. Prompts and
deterministic merge gates now hold the boundaries.

The incidents repeat a few shapes. A load-bearing step was done in prose. An
empty or unknown answer was read as a real one. A parked state did not read
back as itself. A check could never fail. A guard ran from the code it was
judging. A recovery path had never been run.

For jidoka, the lessons that carry over most are these. A parked lap must be
a state the factory reads back, and every route into it notifies someone.
Unknown must never read as done or as nothing to do. The validator and the
rules it enforces must come from the epic branch's base, not from the task
branch. Holdouts need a home builders cannot read, and beads is not that
home. Caps should count across parks. The pass needs its own stage that runs
every holdout on the epic branch.

## Sources and how to read the citations

- `asf:<path>` is a file in `reference/ai-software-factory` at its checked-out
  commit `13d7970`, dated 2026-10-19. GitHub:
  <https://github.com/coleam00/ai-software-factory/tree/13d7970653b2d9dcec23d7fbd168607a87e09f3e>.
- `asf@<commit>:<path>` is the same repo at an older commit. Most early
  citations use `9d1f7cd`, dated 2026-09-03, the last snapshot with the
  factory's own workflows before they moved to Archon.
- A bare seven-character hash is a commit in that repo. Its message body
  often carries the incident.
- `archon:<path>` is Archon at `9d8aaf56143b6a7ea8af90f1e6c472ae26653f85`,
  the revision `asf:template/factory/pack.json` pins. The reference repo hands
  every stage to Archon, so the current lap cannot be described without it. I
  read it from a local clone at exactly that commit. I did not check that
  GitHub serves the commit. The path on GitHub would be
  <https://github.com/coleam00/Archon/tree/9d8aaf56143b6a7ea8af90f1e6c472ae26653f85>.
- The transcript breakdown in `docs/transcripts/my-ai-dark-factory-dream-is-dead.breakdown.md`
  is what the video claims. Where the repo disagrees, the repo wins here.

The repo carries no license file, so this note paraphrases and quotes little.

## A word on vocabulary

The reference and jidoka use "lap" for different things. In the reference a
lap is one run of `archon-loop`, which makes one move on one item: build it,
fix it, or find nothing. An item can take several of those before it merges.
A jidoka lap is one task's whole trip from build to merge into the epic
branch, retries included. So one jidoka lap is closer to all the reference
laps one item gets. The reference manager also calls each of its runs a
"pass", which is not a jidoka pass. Below, "lap" means the reference's lap
unless the sentence names jidoka.

## How the design changed

| Dates | What ran a lap | Commits |
|---|---|---|
| 2026-08-31 to 09-06 | Five workflows the factory wrote itself, run on Archon. A Python dispatcher with no model chose the next action from GitHub labels in a fixed priority order. Labels were the state machine. | `fd74a9d`, `1ed3131`, `0ca7e38` |
| 09-07 | The factory dispatched Archon's shared SDLC pack and kept its own state machine, caps, gate and dial. | `31d25b9` |
| 09-08 to 10-13 | A thin consumer of a pinned Archon. `archon-lifecycle` composed triage, delivery, runtime and holdout checks, bounded repair, discoveries, a merge queue and deploy. Scheduling moved to Archon triggers on 10-07. | `30c13ea`, `32e92c9`, `13bdd50` |
| 10-14 to now | `archon-loop` with parallel laps, and `archon-manager` on a slower schedule. | `5d0d475`, `e3af3f3`, `13d7970` |

The pitch changed too. The first README promised that nobody reads the diff,
with an autonomy dial whose target was auto-merge at level 3
(`asf@9d1f7cd:README.md`). On 10-15 the opening was rewritten. The human now
plans the release and tests it in staging, and the factory runs the middle
(`e270043`). That matches the video's move from a dark factory to a software
factory. It also matches jidoka's handoff and acceptance.

## The stages of a lap

### The first design, workflow by workflow

The dispatcher answered one question per tick, and no model took part in the
answer. Its order was to fix a failed PR, validate an open one, merge a passed
one, implement an accepted issue, then triage. Finishing work came before
starting work, because the reverse triages forever while PRs rot
(`asf@9d1f7cd:template/factory/state.py`, `next_action`;
`asf@9d1f7cd:template/factory/dispatch.py`).

Each kind of work was its own workflow, so each ran in its own process,
worktree and context:

| Workflow | Stages | Source |
|---|---|---|
| `factory-implement` | resolve, preflight that refuses if a secret file is not ignored, prime on the small tier read-only, plan on the large tier with no shell, a plan gate that cancels the run on an escalation, implement on the medium tier, commit as a script that fails on an empty diff, guard for protected paths and size caps, a full self-check gate, review by including Archon's `archon-review`, a PR record, open PR by script | `asf@9d1f7cd:template/.archon/workflows/factory/implement/factory-implement.yaml` |
| `factory-validate` | resolve, prepare with narrow fetches and governance read from the base branch, run the gate, compose a brief, a judge with no tools, then a script that applies the verdict | `asf@9d1f7cd:template/.archon/workflows/factory/validate/factory-validate.yaml` |
| `factory-fix` | resolve, prepare that checks the attempt cap and that findings exist, fix, land, which hands the PR back to `open` for a fresh validation | `asf@9d1f7cd:template/.archon/workflows/factory/fix/factory-fix.yaml` |
| merge | `factory/merge.py`, a script that reads a verdict file and squash-merges. A model never decides to merge. | `asf@9d1f7cd:template/FACTORY_RULES.md` section 3 |

Fix was a separate workflow on purpose. A fix that runs inside the judging
process inherits the judge's reasoning, and the next validation then judges a
tree built with its own earlier opinion in context. Findings reached the fixer
as a file on disk (`asf@9d1f7cd:template/factory/config.py`, comment above
`WORKFLOW_FIX`).

### The current lap, `archon-loop`

| Stage | Kind | What it does |
|---|---|---|
| pick | agent | Reads the whole board and returns one move, a route, a confidence and the area the work will touch. The route is `continue` for an open PR, `simple`, `complex` or `none`. Pick writes a `Contract` comment when an issue's criteria are not checkable. |
| claim | script | Posts a claim comment and holds the item only if this run's claim is the oldest live one. |
| build | agent | The in-loop builder, for `continue` and `simple`. It ends by naming the PR or saying there is none. |
| ship | included workflow | `archon-ship` for `complex`, covering triage, investigation or planning, implementation, multi-lens review and CI. |
| subject | script | Records the PR, its head, its base and the files it changes, so the app check tests facts rather than the PR's description. |
| check-app | agent | Black-box test of the PR merged with the current default branch. It covers each contract criterion, the holdout scenarios the change could affect, probes of every new state, and every defect it sees. It saves evidence files and returns structured lines. |
| evidence | script | Checks that every line cites a file written during the check, that every cited image was opened, and that the overall verdict agrees with the lines. |
| review | agent | Reads the diff and gives every non-passing line a disposition. It decides merge, send back, or return to the owner. It never merges. |
| land | script | The merge gate. It merges the reviewed commit only if the record supports it, the head is that commit, and it contains the current default branch. A refusal is posted as a comment the next lap reads. |
| deploy | included workflow | Optional `archon-deploy` after a merge. |
| release | script | Frees the claim however the run ended. |

Source: `archon:.archon/workflows/sdlc/loop/archon-loop.yaml` and the four
prompts in `archon:.archon/workflows/sdlc/loop/commands/`. The README
describes the same lap in one paragraph (`asf:README.md`, "Current status").

Two of these are worth noting. The app check runs before the code review, and
it may look at the diff only after its last test, so it tests what the change
does rather than what it says (`archon:.../loop/commands/loop-check-app.md`).
And the merge decision is split between a model that decides and a script
that refuses. The script's header says why. Left to merge on its own, the
reviewer merged over defects the app check had seen, over a pipeline whose
review step had crashed, and onto a default branch that had moved since
anything was tested (`archon:.../loop/scripts/land.ts`).

The video's fix loop matches the code. Anything sent back comes around as a
`continue` move, which the in-loop builder handles even for a complex item.
Routing only escalates. An item a simple attempt failed on becomes complex
and never goes back (`archon:.../loop/commands/loop-pick.md`, "Route").

The video says a cheap classifier called Jev does triage. Neither repo
mentions Jev or any classifier. At this pin the pick stage is an LLM on the
workflow's `large` tier that returns a route with a confidence, and low
confidence on `simple` means route it `complex`. Whether Cole runs Jev outside
this code is unconfirmed.

## Holdout scenarios

### First attempt, a directory builders are denied

The holdout lived in `.factory/holdout/HOLDOUT.md`. Every builder node denied
`Read`, `Glob` and `Grep` on that path. So did the review pack the implement
workflow included. An include adds its deny list to every node it expands
into, and the workflow comment warns that without it a reviewer could quote a
holdout assertion into a report the fixer then reads
(`asf@9d1f7cd:template/.archon/workflows/factory/implement/factory-implement.yaml`,
the `review` node). `bin/audit.py` failed any node that could read files and
had no holdout deny (`asf@9d1f7cd:bin/audit.py`).

The validator was kept apart in six layers, listed at the top of
`asf@9d1f7cd:template/.archon/workflows/factory/validate/factory-validate.yaml`.
It ran as a separate run with its own worktree. It fetched the PR without
comments, reviews or commit bodies. It read governance from the base branch
before checking out the PR. The judge had no tools. A tripwire failed if any
builder artifact showed up. When the raw markers and the judge disagreed, the
markers won. The tripwire's first version matched on filename and fired on the
workflow's own `plan.md` prompt. The rule then moved to provenance. An
untracked file shaped like a builder artifact is a leak, and a tracked one is
not (`asf@9d1f7cd:template/factory/tripwire.py`).

My reading is that the wall had a gap the repo never names. The implement and
fix nodes had `Bash`, with only `git` and `gh` denied, so a shell `cat` of the
holdout was not blocked. The repo later stopped claiming the wall at all. The
current README says a directory called "holdout" does not make it private and
asks for real isolation from the builder. The shipped `HOLDOUT.md` says no
factory helper enforces a private boundary (`asf:README.md`, section 3 of the
agent instructions; `asf:template/.factory/holdout/HOLDOUT.md`). Commit
`fe9b83c` is titled "stop claiming a trust boundary the code does not have".

### Now, a file outside the repository

The loop takes `holdout` as an input, a path outside the repository that only
the app check reads (`archon:.../loop/archon-loop.yaml`, `inputs.holdout`).
The server guide puts it under `/root/private` with mode 700
(`asf:docs/server-cheat-sheet.md`, step 8). The builder's prompt forbids
reading files outside the repository other than the runtime instructions
(`archon:.../loop/commands/loop-work.md`, "Never"). The app check and the
reviewer must never quote a scenario, its steps or its thresholds in a PR, an
issue, a commit or the report. A holdout line carries only the scenario id, a
verdict and what a user sees (`loop-check-app.md`, `loop-review.md`).

The manager owns the set (`archon:.archon/workflows/sdlc/manager/commands/manage.md`):

- Holdouts come before the work. When a section of the product document has
  been sliced into issues and has no scenarios, the manager writes them from
  the document, not from the issues, before laps build it. A scenario that
  repeats an issue's criteria is not a holdout.
- Each pass it runs every scenario on the default branch and writes
  `holdout-baseline.md` beside the holdout. App checks read that file to tell
  a failure the default branch already has from a new one.
- A defect that got past review gets an issue and a new scenario, written
  about the behavior and the cases around it, so a builder working to the
  issue's wording does not pass it by construction.
- It may add and tighten scenarios, never loosen them. A loosening, any edit
  to an owner's scenario, or a suspension is an owner question with no
  default.

This privacy rests on paths and prompts. Archon runs Claude Code in
`bypassPermissions` (`archon:packages/docs-web/src/content/docs/reference/security.md`),
and the loop's nodes set no tool restrictions, so a builder running as the
same OS user could read the file if it ignored its prompt. That is my
inference. The repo does not discuss it.

### What the holdout incidents taught

- Assert exact figures worked out by hand, not a property. A holdout that
  checked "balances sum to zero" let through a defect that returned only the
  first expense, because a subset also sums to zero. The mutation runner
  found it, not reading (`asf:docs/incidents.md`, "The mutation that
  escaped").
- Give the holdout a fresh app and a fresh database. It once ran on the app
  the journeys had just filled and saw seven links where it expected three
  (`9df9259`).
- Check that the holdout is still wired in. Both end-to-end rungs were
  deleted and the self-test and audit stayed green, because both checked the
  code that reads evidence and nothing checked that anything still produced
  it (`asf:docs/incidents.md`, "Both end-to-end rungs were deleted").
- Do not reject an honest pass. An evidence check refused any observation
  equal to its expectation, which is what every honest pass of a numeric
  assertion looks like. A factory that had earned auto-merge could merge
  nothing (`asf:docs/incidents.md`, "The evidence check called an honest
  measurement a fabrication").

## Caps, and what happens at each

### The current loop

| Cap | Value | At the cap | Source |
|---|---|---|---|
| Attempts on one item without progress | 3 | Pick labels it `needs-owner`, comments what blocks it and the decision that would unblock it, and picks the next move | `archon:.../loop/archon-loop.yaml`, `loop-pick.md` "Caps" |
| Send-backs plus merge-gate refusals | 2 | The same. The reviewer returns the item to the owner instead of sending it back a third time | `loop-pick.md`, `loop-review.md` |
| Claim age | 6 hours | A claim from a run that died stops holding the item | `archon-loop.yaml`, `claim_hours` |
| Agent node idle time | 45 minutes | The engine fails the node | `archon-loop.yaml`, `idle_timeout: 2700000` |
| One wait inside the app check | 10 minutes | Step in batches. A check left running in the background makes the report due at once | `loop-check-app.md` |
| Reviewer's CI wait | 20 minutes | `gh pr checks --watch --fail-fast` bounded | `loop-review.md` |
| Parallel laps | 1 to 8, default 1 | A tick that finds every slot busy is skipped, not queued | `asf:template/factory/consumer.py`, `trigger_config`; `ded543c` |
| Lap that ends within 5 minutes on an unchanged board | 300 seconds | The next tick waits for the board to change | `consumer.py`, `EMPTY_LAP_SECONDS`; `4d6ad7d` |
| Launch stuck in `pending` | 10 minutes | The scheduler abandons the run so its slot frees | `consumer.py`, `sweep_stuck` |
| Idle bookkeeping lap | 60 minutes | One lap starts even with nothing workable | `consumer.py`, `idle_pick_minutes` |

The manager has caps of its own. It creates at most 5 issues and rewrites at
most 5 per pass. It abandons a run that never started after 30 minutes, and it
reports a run stuck on one node for over 3 hours without killing it. It
resumes a run that failed on infrastructure once. When the same kind of
finding comes up three times, it opens one issue to turn it into an automatic
check. It applies an owner question's default after 48 hours, except for
direction, scope and look and feel (`manage.md`).

### The first design

| Cap | Value | At the cap | Source |
|---|---|---|---|
| Fix attempts per PR | 2 | The dispatcher escalates to `needs-human`, writes `needs-human.md`, notifies | `asf@9d1f7cd:template/factory/state.py`; `FACTORY_RULES.md` sections 7.2 and 8 |
| Production lines, total lines, files per PR | 500, 1500, 12 | The guard rejects the PR. Tests stopped counting toward the 500 after PR #14 was rejected at 515 lines, 404 of them tests | `asf@9d1f7cd:template/factory/config.py`; `0ca7e38` |
| Issues per day from a non-owner | 3 | Labeled `factory:rate-limited`, looked at again after midnight | `FACTORY_RULES.md` section 1 |
| Concurrency and poll interval | 1 and 30 minutes | Slower than feels right, because a fast loop multiplies a mistake before anyone sees it | `FACTORY_RULES.md` section 8 |
| Watchdog over a 120-minute window | One action on one target dispatched 3 times with no run completing, or 6 times whatever the outcome. 5 settled runs in a row with none completed. 8 dispatches with none completed. $25 spent, or $8 spent with nothing completed | Writes `.factory/STOP`, records a halt, notifies. The next tick refuses to run | `asf@9d1f7cd:template/factory/watchdog.py` |
| Gate deadline | 3600 seconds, an operator setting | The gate stops the process tree it started and exits as an environment failure, never as a product failure | `asf:docs/incidents.md`, "The fixed deadline that interrupted a complete gate" |

### What the cap incidents taught

A cap is only as good as the state it parks in. The watchdog exists because
the dispatcher validated one rejected PR 68 times in three and a half hours
and spent $17.18. Each tick was correct. Escalation wrote `needs-human`, but
the PR state table did not list `needs-human`, so the PR read back as `open`
and went to the front of the queue again. The fix added the state and a
round-trip check that every state, written as its label, reads back as
itself. The first version of that check went vacuous rather than red,
because it generated its cases from the very list it was auditing
(`asf:docs/incidents.md`, "The escalation that fed the queue it was supposed
to leave"; `asf@9d1f7cd:template/factory/watchdog.py` docstring).

A hold is a state, not a message. The gate computed "do not auto-merge",
posted a careful comment, then set the PR to `passed`, which is exactly what
the dispatcher merges. It merged 45 seconds later. Nothing errored
(`asf:docs/incidents.md`, "The hold that was only a sentence").

An attempt that ran is an attempt spent. Three fix runs in one night each
diagnosed correctly that the red gate was inherited. The land step failed
each one as "changed nothing" and sent the PR out again, and the attempt
counter never moved. The watchdog halted the factory (`45e8faa`).

A run that dies without a result must park its item. One provider error held
a lock forever and wedged a factory at capacity 1 (`c46fba8`).

Some caps never applied. The runner passed `--max-turns` to every node, and
the agent accepted it, ignored it and exited 0. The repo's advice is to verify a flag before
relying on it, and to prefer a spend ceiling to a turn ceiling
(`asf:docs/incidents.md`, "The cap that silently did not apply").

A person releasing a parked item is not a broken rule. The watchdog halted a
real box 27 seconds after a human unparked something by hand. The fix
treats a parked label's absence as the human's signature (`e512cca`).

## The manager

The video says the manager runs every two or three hours. The pack says "a
slower schedule than archon-loop (every few hours)"
(`archon:.archon/workflows/sdlc/manager/archon-manager.yaml`). The consumer
schedules one workflow from `.factory/schedule.json`, so how an install runs
the manager on its own cadence is not in this repo. That part is unconfirmed.

`archon-manager` is one agent node on the large tier with a fresh context and
a 45-minute idle timeout. Its prompt, `manage.md`, gives it five jobs.

1. Look at everything. That means issues and PRs open and recently closed,
   what merged, CI on the default branch, the product document, the mission,
   the running product, and the holdout. Then it asks whether the product is
   getting better. It looks for what is stuck, what keeps coming back, what
   got past review, and whether the order of work is still right.
2. Keep the loop healthy. It abandons runs that never started and resumes
   once a run that failed on infrastructure with its worktree intact. It does
   not resume a run that failed on a used-up usage limit or on the work
   itself. It reports hung runs without killing them. It stops leftover app
   instances by PID, only ones the runtime started and no live run owns. It
   reports streaks of empty laps so the owner can pause launches. When an
   item has had more laps than the attempt limit, counted across every park
   and unpark, the manager stops unparking it and takes it to the owner. The
   exception is wording the loop wrote, such as a `Contract` or a
   `Depends on`. When that is what keeps failing, the manager may narrow the
   item once.
3. Act on GitHub. It closes duplicates, rewrites unclear criteria while
   keeping their intent, fixes the order with `Depends on` lines, and nudges
   or closes PRs idle over 24 hours. It opens one root-cause issue in place of
   a run of patches. It owns the holdout set as described above. It opens a
   top-priority issue when the default branch is red.
4. Keep one open issue called "Owner decisions needed". Each question has
   options, a recommendation and a default that applies after 48 hours,
   except questions about direction, scope or look and feel.
5. Append one metrics line per pass to a "Loop metrics" issue. It counts
   merges by route, open PRs, send-backs, merge-gate refusals, ship
   correction rounds, open `needs-owner` items, owner questions, default
   branch health, empty and failed laps, and health actions.

It may never edit product code, the harness and its scenarios, CI, the
mission or the product document. It may never touch a claim comment, kill
processes by name, or touch the owner's desktop.

Before the manager existed, the first design split this work across code.
The dispatcher reported stalled items before anything else. `watchdog.py`
read an append-only ledger of dispatches, settles and escalations at the top
of each tick. `monitor.py` printed only what an operator should act on
(`asf@9d1f7cd:template/factory/dispatch.py`; `watchdog.py`;
`template/.factory/monitor.py`). The watchdog's design rule carries over to
any supervisor. It was a pure function of a list of events and a clock, so a
test could hand it a synthetic history and watch each detector fire.

## Parallel laps

### The first design ran one at a time

Concurrency was 1. A lock per workflow and target was created with
`O_CREAT | O_EXCL`, which avoids a check-then-write race. It was tested only
when two dispatcher loops ran for 45 minutes by accident and dispatched each
unit once (`asf:docs/incidents.md`, "The race that was finally run, by
accident"). That lock does not stop two dispatchers. Three copies of the loop
once merged one PR three times inside three seconds, and the refusals
escalated a PR that had merged fine. The loop became a singleton with a pid
file that clears itself when stale (`asf:docs/incidents.md`, "Three
dispatchers, one merge"). An issue that a live PR already answers is not
work, or the dispatcher opens a second branch for it (`asf:docs/incidents.md`,
"Two laps for one issue").

### The current loop runs up to eight

- Slots. Archon admits at most `parallel` laps per repository and workflow,
  and a tick that finds them all busy is skipped
  (`asf:template/factory/consumer.py`, `trigger_config`; `5d0d475`). The
  server guide still says such a tick is queued, which was true before
  `ded543c` (`asf:docs/server-cheat-sheet.md`, step 11).
- Claims. A run posts `Loop claim: run <id>` with its route and area, waits
  five seconds for a rival's claim to become readable, and holds the item
  only if its claim is the oldest live one. A loser withdraws and does
  nothing this lap (`archon:.../loop/scripts/claim.ts`).
- Areas. Pick never chooses a claimed item, and it avoids items whose change
  would land in the same files or module as a live claim's area. When
  everything overlaps, the route is `none` (`loop-pick.md`). This is the
  model's judgment, not a lock.
- One pick at a time. The scheduler once launched a second lap while the
  first was still choosing. Both picked the same item and the second lost
  the claim race. Now a lap launches only when no lap is still choosing, so
  the next tick sees the first claim (`06e4fec`; `consumer.py`,
  `launch_decision`).
- Release. A release step runs however the lap ended, and the scheduler
  releases claims of runs that ended without releasing them
  (`archon:.../loop/scripts/release.ts`, `workable.ts`).
- Integration. The app check tests the PR merged with the current default
  branch. The merge gate refuses a head that does not contain the default
  branch, and it refuses a merge result that differs from what was tested in
  files this change touches. Builders bring a branch up to date by merging,
  never by rebasing or force-pushing (`loop-check-app.md`, `land.ts`,
  `loop-work.md`).
- Runtime. Several checkouts must be able to run the app at once, with a
  port and pid file per checkout (`asf:README.md`, Commands).

## Permissions when nobody is watching

### The first design allowed and denied per node

The workflows set `allowed_tools` and `denied_tools` per node, and the
comments record what probes proved. `Bash(python:*)` in the allow list
granted no shell at all. `Bash` granted one. `Bash(git:*)` in the deny list
did block git. So the grant was coarse and the deny list did the limiting.
The first version scoped the grant instead, and the build nodes ran for
weeks with no shell. They said so politely and exited 0
(`asf@9d1f7cd:template/.archon/workflows/factory/implement/factory-implement.yaml`,
comment on `prime`). The plan node got no shell at all. A planner with one
planned to measure things itself, was refused, and the refusal went to a
human who was not there. The judge had no tools. Builders could
not run `git` or `gh`, and scripts did the commit, push, PR and merge.

The agent that drove the app's journeys shipped with
`claude -p --permission-mode acceptEdits`. That mode refuses `Bash`, so it
could not send a single request, and it said so in every assertion. It did
not claim a pass, which is the behavior the rung relies on. Adding
`--allowedTools Bash,Read,Write` worked. `bypassPermissions` also worked and
grants more than the rung needs (`asf:docs/incidents.md`, "The journey agent
shipped with a permission mode that could not run curl"). Codex's sandbox was
a private PID namespace, so a sandboxed Codex could not restart the app it
was testing (`b189581`).

### Now Archon skips permission checks and gates do the limiting

Archon runs Claude Code in `bypassPermissions`. Its mitigations are a git
worktree per run and optional per-node tool limits
(`archon:packages/docs-web/src/content/docs/reference/security.md`). The loop's
nodes set no tool limits (`archon-loop.yaml`). The boundaries are now three.

- Prompt rules. Every loop prompt ends with a "Never" list. Between them
  they forbid editing the judge, CI, the mission or the product document,
  touching claim comments, killing processes by name, waiting without a
  timeout, and touching the owner's desktop.
- Deterministic gates. `protected_paths` in `harness/harness.config.json`
  holds any PR that touches a match for a human. The README says review did
  not reliably notice an agent editing the files that govern it, and that a
  reviewed delivery once rewrote `engineering.md` and merged
  (`asf:README.md`, "Protected paths"; `148be40`). The loop's reviewer must
  name any change to what a check samples, skips or measures, and the merge
  gate refuses one with no owner approval (`loop-review.md`, `land.ts`).
- The host. Claude Code refuses to run unattended as root without
  `IS_SANDBOX=1`. The timer unit sets it and reads the token from a mode-600
  file outside the repository (`asf:README.md`, "The timer on Linux";
  `efb95a1`).

The rules file also keeps an irreversible list that always stops for a
human: changes to identity or authentication, and migrating or deleting
stored data (`asf:template/FACTORY_RULES.md`). The first design's list also
covered moving money and public side effects such as a sent email
(`asf@9d1f7cd:template/FACTORY_RULES.md` section 7.3).

## What the incident notes say went wrong

`docs/incidents.md` runs to about 1700 lines. It opens by saying that every
rule in the repo exists because something broke, and that what looks like
paranoia is a scar. These are the shapes that recur, with the entry titles
to find them.

1. A load-bearing step done in prose. The hold was a comment while the state
   said `passed`. `Fixes #10` sat in a code span, so GitHub never closed the
   issue, which was labeled done. A rejection built in a shell pipeline
   reached its filer as `@-`. The repo's rule is that a step that must happen
   does not depend on someone else's parser ("The hold that was only a
   sentence", "The closing keyword that was formatted as code", "The correct
   rejection that reached the filer as two characters").
2. Empty or unknown read as an answer. An empty run list released every lock
   one tick after it was taken. A `not_found` status, correct for releasing a
   lock, leaked into the progress detectors and halted a healthy factory
   while three PRs merged. A staleness check printed "current" after its fetch
   failed. The rule is three branches, never two: behind, level, and could
   not tell ("The empty answer that was read as a negative answer", "The
   watchdog's first act was to halt a healthy factory", "The staleness check
   that called an unanswered question current").
3. States that did not read back. These are the 68 validations above, and a
   transition table enforced only in a command-line wrapper while eleven
   callers imported the function directly. The fix enforces at the write,
   using data fetched at the moment of writing ("The transition table that
   governed only the callers that asked").
4. Checks that could not fail. An import check passed a quoted string to
   `python -c`, so Python evaluated a string literal and exited 0.
   `compileall` reported static checks green on a JavaScript repo. A
   mutation aimed at one rung was caught by another. Two guards hid each
   other's removal. The self-test once defended the wrong behavior with a
   comment explaining why. The repo's rule is to point every new check at
   something that must fail before trusting it ("The import check that could
   not fail", "Aimed at a rung, landed on another", "Two guards that made
   each other invisible").
5. Whose copy is running. The guard that rejects PRs touching protected files
   was imported from the PR's own checkout. One commit switched it off and it
   printed both violations, then passed. It now runs from the base ref and
   fails closed if it cannot. A routine sync later deleted the
   project's protected-path list because it lived in a file the sync
   overwrites ("The guard could not guard itself", "A routine sync deleted
   the protected-path list").
6. Liveness guessed wrong. Detached dispatch made the recorded pid useless,
   but a docstring still said the pid protected live laps, and the reaper
   killed them at five minutes. Runs launched by hand died with the shell. A
   cancel said it could not reach a run, and an operator abandoned it on
   that word and killed a healthy lap ("The reaper whose docstring explained
   why it was safe", "The runs that died with the shell that started them",
   "The cancel that reported no live owner").
7. Gates with the wrong error rate. One session held 100% of merges, and all
   three hold rules were wrong. One counted lines for assumptions and showed
   80 where there were 8. One held the PRs that added tests. One regex never
   matched. A floor raised to the most thorough run's assertion count would
   fail every ordinary run after it, because the agent chooses that count per
   run. The repo's conclusion is that a gate's error rate is a measurement,
   found only by running the factory for a day ("The autonomous factory that
   needed a human for everything", "The ratchet would have climbed to the
   luckiest run").
8. Recovery never run. Rollback had never executed and was wrong four ways.
   It left a staged revert, produced a hybrid tree, failed opaquely, and left
   a pointer that made the next deploy a no-op. A merge path moved a branch
   pointer with `update-ref` under the main checkout, so the next commit by
   anyone reverted the merge, and one did, wiping a feature and 106 lines of
   tests. The alarm reported delivery for messages the server rejected,
   because `curl -sS` exits 0 on HTTP errors ("Rollback had never been run",
   "The merge that armed a revert in your checkout", "The alarm reported
   success").
9. Escalation that never reached anyone, or reached them too often. A
   correct `needs-human` triage sent no notification, because the notifier
   sat only on the failure path. One 30-second GitHub 503 paged a human. The
   fix retries 5xx errors, timeouts and resets three times, and never retries
   an answer such as a 404, a 422 or a refused merge ("The escalation that took
   the success path", "A thirty-second GitHub wobble").
10. A starved queue that looked dead. An earlier factory logged "nothing to
    dispatch" every 30 minutes for three months, because a benchmark had
    labeled every issue in progress as a lockout and nobody lifted it
    ("The factory that was starved, not broken").

The later commit messages carry incidents too. Two laps that failed in
seconds on a used-up usage limit made the launch gate report "nothing to
start" for hours, until failed laps stopped counting as empty ones
(`ce369bc`). Items the gate counted as workable, but that pick stayed clear
of, bought an empty lap every tick (`4d6ad7d`). A head that could not contain
its base was approved and refused in turn for as many laps as anyone paid
for, until it was held for a person (`675063c`).

## Crashes, usage limits and outages

The repo says this much.

- Dispatch detached. Every lap that died mid-node was started by hand
  without `--detach`, so it died with its shell and left its row reading
  `running`. A live run is told from a dead one by writes in its worktree,
  not by log silence, because some gate stages print nothing for ten minutes
  (`asf:docs/incidents.md`, "The runs that died with the shell").
- Report a stall. A label that means "being worked on" needs something that
  notices when nothing is working on it. A run once died mid-lap and left its
  issue reading "in progress" for 86 minutes. The dispatcher reported it as
  stalled instead of moving on, and the repo credits that kind of report with
  turning a three-month outage into a five-minute one
  (`asf:docs/incidents.md`, "The run that died between two nodes").
- Make applying a result resumable. In the second design a dispatch wrote a
  journal before asking the engine anything, and applying a verdict was
  resumable effect by effect, so a crash between two of five writes retried
  only the three that did not land (`31d25b9`).
- Resume waits on each tick. Each timer tick runs `archon trigger fire`, then
  `archon workflow wake`, which resumes runs paused on a CI check or a usage
  limit. `pause` stops launches but keeps waking. `halt` blocks launches and
  continuations. Disabling the timer instead strands a lap in flight
  (`asf:template/factory/consumer.py`, `schedule fire` and `pause`;
  `03a6e6e`).
- Clean up after a launch that never started. The scheduler abandons a
  `pending` run whose launch log ends in an error after ten minutes
  (`consumer.py`, `sweep_stuck`). The manager is the backstop for anything
  the scheduler missed, and it resumes infrastructure failures once.
- Read the board with a fallback. If the launch gate cannot read the board,
  it launches anyway, the way the scheduler behaved before the gate existed
  (`consumer.py`, `launch_decision`).

Archon's documentation at the pin fills in the engine side. AI nodes retry
transient failures twice with backoff. Rate limits get at least five retries
at about 45 seconds each, and an overloaded provider gets five retries over
about 15 minutes. Script nodes never retry unless a node opts in, so a
side-effecting script is not run twice by accident
(`archon:packages/docs-web/src/content/docs/guides/authoring-workflows.md`,
"Retry Configuration"). A used-up quota is terminal for the attempt. With
`autoResumeOnQuotaReset` on, a typed quota failure from Claude or Codex
schedules one continuation at the reset time, within 24 hours by default.
The setting is off by default
(`archon:packages/docs-web/src/content/docs/reference/configuration.md`).
The consumer's comments assume runs paused on a usage limit get resumed. I
found nothing in the factory that turns that setting on, so whether an
install resumes after a usage limit is unconfirmed.

## Model routing

The first design routed by tier per node, never by model id, so a provider
swap kept working. Prime and sorting ran on the small tier, plan on the large
tier, and implement and judge on the medium tier. The reason given is that
two slots decide quality, planning and implementing. A premium model in one
of them buys most of the quality of both (`asf@9d1f7cd:template/factory/config.py`,
`MODEL_PLAN` and the comment above it). When the factory moved to Archon's
pack, those four settings were connected to nothing and were deleted. A knob
that reports a value it does not apply is the worst kind (`5a848b3`).

Now each Archon workflow names its tier. `archon-loop` and `archon-manager`
run every agent node on `large`. `archon-ship` includes triage, investigate,
plan and deliver, and deliver includes implement and review. Of those,
`archon-plan` and `archon-implement` use `large`, and `archon-review` uses
`medium` with its code lens on `large`. Triage, validation and the merge
queue use `medium` (`archon:.archon/workflows/sdlc/*/archon-*.yaml`). The README suggests Sonnet
for small and medium and Opus for large, and the server guide gives GPT-6
Astra on every tier for Codex, with high effort on large
(`asf:README.md`, "Configure Archon"; `asf:docs/server-cheat-sheet.md`,
step 7).

One measurement is in the history. On two live laps, Opus on the large tier
was about half of a roughly $12 lap, at about 2.3 times Sonnet's cost per
token. A change made Sonnet the default for large. Cole reverted it the same
day, judging Opus worth the cost (`c3824c2`). The first README was blunter.
It said cost projections are wrong by 10 to 20 times, always in the same
direction, so instrument tokens on day one
(`asf@9d1f7cd:README.md`, "Cost").

## What bears on jidoka

jidoka takes one epic at a time from beads, runs a lap per task into the epic
branch, then the epic's own stages, then hands the epic back for acceptance.
Several of the reference's hardest problems shrink under that shape. A few get
sharper.

### Take these

1. Make every lap ending a bead state the factory reads back as itself, and
   test the round trip. The glossary already names merged, parked and
   interrupted. The 68-validation incident is what happens when parked reads
   back as open. And the absence of the parked state after a human acts
   should count as the human's release, not as a fault (`e512cca`).
2. Send every route into "parked" through one helper that notifies and reads
   its own write back. The reference found five routes into `needs-human`,
   and one of them, a correct triage, notified nobody
   (`asf:docs/incidents.md`, "The escalation that took the success path").
3. Give every read three answers: yes, no, and could not tell. A failed
   `bd ready` is not an epic with no ready tasks. The starved-queue incident
   says to check the input queue before calling the machine broken.
4. Count a task's attempts and send-backs across parks and interruptions. A
   jidoka lap includes its retries, which is the manager's rule in
   `manage.md`, and an attempt that ran is spent (`45e8faa`). At the cap,
   park the task with the question that unblocks it and a proposed answer.
   Do not stop the factory for one task.
5. Run the judge from the base. The rules files, the gate scripts and the
   guard should come from the epic branch, never from the task branch under
   test. Enforce protected paths with a script at merge. In the reference,
   review alone let an agent rewrite `engineering.md` and merge. In this
   repository the protected set would include `AGENTS.md`, `CLAUDE.md`,
   `GLOSSARY.md` and the ADRs.
6. Split the merge decision. A model decides, and a script refuses unless the
   record holds: evidence files written during this check, the head pinned
   to the reviewed commit, and that head containing the current epic branch.
7. Validate before review, and validate black-box. Test the task branch
   merged with the epic branch. The app check reads the diff only after its
   tests.
8. Keep holdouts out of beads. Any agent with `bd show` can read an epic's
   description, so the holdout cannot live in the epic bead or its tasks.
   It needs a path outside every worktree, given only to the validation
   stage. And since the reference's current privacy is a prompt, jidoka
   should decide whether a prompt is enough or the builder needs a real deny
   list. The first design's deny list is the model to copy, with `Bash`
   reads closed too.
9. Make the pass's epic-level stage the manager's holdout duty. Laps run only
   the holdouts a change could affect. The pass runs all of them on the epic
   branch, records a baseline that laps cite for failures the branch already
   has, and adds a scenario for any defect that got past review. It may
   tighten scenarios, never loosen them.
10. If laps run in parallel within an epic, let only one choose its task at
    a time, and have each declare the area it will touch. Claim with
    `bd update --claim`, which its help text calls atomic. The same text
    says it is idempotent for the same actor, so if every lap runs as one
    beads actor, two laps could both succeed at claiming one task. That
    trap comes from the help text, and I have not tested it.
11. Treat a failed lap as different from an empty one, and a usage limit as
    an interruption, not a failure of the work. Resume an infrastructure
    failure once. Start the next lap from what the last one learned. The
    reference posts a lap's triage or plan even when no PR came out of it
    (`7a54303`; `loop-review.md`).
12. Route models by stage tier, keep escalation one way from simple to
    complex, and measure the cost of a lap before raising parallelism.
13. Measure the park rate on the first epics. A gate that parks everything is
    an off switch, whatever its docstring says.
14. Verify every permission and every limit by a probe that must fail.
    `acceptEdits` blocks `Bash`, scoped grants can grant nothing, and
    `--max-turns` was ignored without a word.
15. Test the recovery paths before the factory needs them. Interrupt a lap
    on purpose and resume it. Park a task on purpose and unpark it.

### Less relevant to one epic at a time

- Cross-epic steering, backlog intake from strangers, flood caps and issue
  deduplication across a whole board. The human plans the epic, and the epic
  is self-contained by the glossary's rule.
- Deployment, rollback and staging. jidoka stops at the epic branch and the
  human's acceptance. The rollback lesson still applies to whatever merges
  the epic branch.
- GitHub specifics: closing keywords, 503 retries, free-plan branch
  protection, claim comments that need a five-second settle. Beads has its
  own failure modes, and the same three-answer rule covers them.
- Windows console windows. The general rule still holds. A factory on the
  owner's machine must never take focus or flash a window, or it gets
  switched off (`cab46bc`).

### Open questions this leaves for the map

- Where do holdouts live, and what stops a builder reading them?
- Does jidoka keep a supervisor apart from the pass, or do the pass's
  epic-level stages absorb the manager's work?
- What is a jidoka lap's attempt cap and send-back cap, and do parks reset
  them? The reference says no.
- Does each lap get its own beads actor, so that claims mean something?
