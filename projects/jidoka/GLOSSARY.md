# jidoka

The tool that replaces tracer. The human plans work with it and hands
that work to its factory. The factory runs the work unattended and brings
the result back for the human to accept.

## Language

### Modes of work

**Planning**:
The mode in which the human and an agent turn an idea into epics and
tasks, settling the words and decisions they rest on. It runs from a
wayfinder map down to one stray bug filed into an epic, and ships no
product code.
_Avoid_: Design, grooming, refinement, intake

**Factory**:
The part of jidoka that works an epic unattended, from its handoff until
the epic reaches the acceptance gate.
_Avoid_: Pipeline, engine, loop

**Acceptance**:
The mode in which the human judges an epic the factory has brought to the
acceptance gate, and merges it, sends it back with new tasks, or drops it.
_Avoid_: Sign-off, approval, QA, review

**Bench**:
The mode in which the human and an agent build one bead together, a task
or a stray bug, with the human answering and approving on the spot. Bench
work is never a lap, and it can run while the factory works an epic. A
bead labeled `bench` waits for bench work.
_Avoid_: Pairing, implement, manual mode, attended mode

### Units of work

**Milestone**:
A bead that holds only epics: a container for planning, which the factory
never takes. Milestones wait only on milestones, as epics wait only on
epics and tasks only on tasks. A wayfinder map is the one milestone that
holds other beads, the questions it resolves before its outcome becomes
epics and tasks.
_Avoid_: Initiative, program, theme, saga

**Epic**:
A bead that holds only tasks, and the unit the factory takes. It is
self-contained: neither it nor any of its tasks waits on an open bead
outside it.
_Avoid_: Release, batch, feature, project

**Task**:
A bead inside an epic that is not itself an epic, whatever its beads type.
A task that waits on the human, or that lacks its Demo line, is still a
task; the factory just does not take it yet.
_Avoid_: Ticket, issue, work bead, item, job

**Handoff**:
The step in which the human gives an epic to the factory. The epic's form
is checked, its factory rules are agreed, and the factory takes it.
_Avoid_: Launch, kickoff, dispatch, submit

**Factory rules**:
An epic's own settings and guidance, agreed at its handoff, which bind the
factory only while it works that epic. A setting is a named value the
scheduler reads, such as the lap limit, which starts from the repo
settings' lap limit and can only go lower. Guidance is prose that every
worker follows and that the Spec check holds each diff to.
_Avoid_: Epic config, run settings, policy, ruleset

**Preset**:
A named set of factory rules that handoff offers as a starting point: the
bug-epic preset for an epic that fixes bugs, and the improvement-epic
preset for an improvement epic. Only the rules script writes the rules a
preset holds, and each change posts a one-line comment on the epic.
_Avoid_: Template, profile, mode

**Lap**:
One task's trip through the factory, from the start of its build to its
merge into the epic branch, retries included. It ends merged, which closes
the task; parked, waiting on the human; blocked, waiting on another task in
the epic; or interrupted, when the factory stopped or paused under it. A task that
did not merge gets a new lap that starts from the work left behind.
_Avoid_: Run, attempt, iteration, loop

**Parked**:
Waiting on the human before the factory goes on. A task or an epic parks
when the factory hits a cap or asks a question, and when the human parks
it to stop new stages starting on it.
_Avoid_: Stuck, on hold, needs-owner, escalated

**Paused**:
Waiting on the clock, for a usage window's reset or the API's return,
while the host still runs. A usage limit, an outage, a billing error or an
auth failure pauses the epic. Nothing new starts on what is paused, and
the factory retries after a back-off of 5, 15 and 30 minutes, then every
hour, and carries on by itself.
_Avoid_: Held, throttled, sleeping

**Stopped**:
No manager running for an epic the factory has taken, because the host is
gone or the human stopped it. Only the human starts it again, and the laps
it was running end interrupted.
_Avoid_: Crashed, dead, down, halted

**Dropped**:
Said of an epic the human gave up on. It closes without reaching main,
its running laps end, and its epic branch stays until the human deletes
it.
_Avoid_: Abandoned, cancelled, withdrawn, killed

**Epic branch**:
The branch that collects an epic's work while the factory holds it. Each
lap merges into it, and landing puts its work on main.
_Avoid_: Feature branch, integration branch

**Pass**:
One trip of an epic through the factory: laps for its tasks, side by side
where their dependencies allow, then the epic's own stages over all of its
work. A pass ends clean, and the epic goes to the human for acceptance,
or it ends with new tasks in the epic, and the next pass begins.
_Avoid_: Round, cycle, sweep, loop; "pass" for a stage

**Stage**:
One step of a lap or of a pass, such as the build or the review.
_Avoid_: Step, phase, node, pass

**Cut off**:
Said of a stage whose worker ended because of an error or an interruption,
not because of its own work. The stage reruns from its start, and the
cutoff is not a try. A usage limit, an outage, a billing error or an auth
failure pauses the epic instead, and counts no cutoff.
_Avoid_: Failed, aborted, killed, crashed

**Track**:
How much of a lap a task goes through: the simple track or the full
track. The simple track is the build, the targeted tests and the merge
gate. The full track adds a research brief before the build, and between
the targeted tests and the merge gate an app check, when a holdout names
the task, then a Spec check. The pass's stages are
the same for every task. Handoff proposes a track for each task by a rule
a script checks, and the human confirms or flips it. A task is simple when
no holdout names it, its Seams line names one seam, and it adds no public
type or public API change; any other task is full. A simple task moves to
the full track only on evidence from its own lap, the targeted tests failing
twice, and the move is recorded in a comment with that evidence. A full task
never moves back.
_Avoid_: Route, path, class, weight, complexity

**App check**:
The lap stage in which an agent tests the running app from outside, against
the holdouts that name the task, before it reads the diff. It runs the app
on the lap's slot and reads no other holdout. A builder whose lap fails
here learns the holdout's id, the verdict and what a user saw, never the
holdout's steps.
_Avoid_: QA, black-box test, validation

**Spec check**:
The stage, in a lap or at the bench, that asks whether a bead's diff does
what the bead says, and nothing more. It ends as pass, send back or
cannot judge. Its send back returns the diff to the builder with
findings; the human's send back at the acceptance gate is a different
act.
_Avoid_: Review, spec review

**Merge worker**:
The worker a lap gets when newer work on the epic branch conflicts with
its own or breaks its tests, and which reconciles the two in the lap's
workspace.
_Avoid_: Merge agent, conflict resolver

**Merge gate**:
The last stage of a lap, a script with no model in it that merges the
task into the epic branch only when the lap's record supports it.
_Avoid_: Land, merge agent, approval

**Protected path**:
A path that no lap may change, so the merge gate refuses a lap whose diff
touches one: any path inside an app's acceptance folder, as the repo
settings name it.
_Avoid_: Locked path, guarded file, read-only path

**Test cleanup**:
The first stage of a pass, which deletes the tests the epic added or
changed that add neither confidence nor communication. Each deletion names
the kept test or acceptance spec that covers the same behavior.
_Avoid_: Test pruning, test pass

**Validation**:
The last stage of a pass: the full test suite with every acceptance spec,
the epic's holdouts and every standing holdout, run on the epic branch.
_Avoid_: Test gate, app check, QA

**Acceptance gate**:
Where the factory's work on an epic ends and the epic waits for the human
to merge it, send it back with new tasks, or drop it.
_Avoid_: Approval gate, sign-off

**Landing**:
Putting an accepted epic's work, or bench work, on main as one commit or
one per task. Bench work runs the full test suite once, at landing, on the
branch rebased on main; an epic's work is tested again if main moved since
validation.
_Avoid_: Merge (a lap merges into the epic branch), ship, release, integrate

**Discovered work**:
A problem a lap or a pass finds outside the task or diff it is working
on. It is filed as a bead linked discovered-from to the task it was found
in, inside the epic when the epic cannot be accepted without it, and
outside the epic otherwise. A worker never files it: its stage ends with a
discovered-work report in its scratch folder, and a script files it. A lap
that cannot finish without its discovered task ends blocked, and the task
waits on the new one.
_Avoid_: Side quest, follow-up, tech debt

### Asking the human

**Question**:
A worker's request for a decision from the human, which parks its task or
its epic. It says what the worker found, the options, each with the
worker's confidence in percent that it is the right answer, and the one it
recommends; unparking without an answer takes the recommendation. A worker
never asks live: its stage ends with a question report in its scratch
folder, and a script posts it on the task. A worker makes the choice as an
assumption instead when the bead, the epic, the glossary or an ADR already
settles it, or when its recommendation reaches 90% and is cheap to reverse.
_Avoid_: Escalation, prompt, ask, blocker

**Assumption**:
A choice a worker makes inside its task without asking, because it is
cheap to reverse and leaves the task's Demo line as it was. Acceptance
shows the human every one.
_Avoid_: Guess, decision, note

**Notification**:
A message telling the human that the factory waits on them: a task or
the epic parked, only parked tasks left, the epic at the acceptance gate,
the factory stopped with work left, the factory paused on a billing error,
an auth failure or an outage past an hour, or the host asking for a
permission while an epic runs. It points at a bead, and the bead carries the
question; missing a notification loses nothing.
_Avoid_: Alert, ping, push, notice

**Page**:
A web page that shows the human the work at a moment that needs them,
such as a question or the acceptance gate, through diagrams and examples.
It sits beside its bead, and the bead keeps the record in plain text.
_Avoid_: Report, artifact, view, explainer, dashboard

### Holdouts

**Holdout**:
A scenario, in prose with exact expected values, of what a user does to
the running app and what they then see. The human approves an epic's
holdouts in planning, each one names the tasks it exercises, and no
builder ever reads one.
_Avoid_: Acceptance test, hidden test, secret test, eval

**Standing holdout**:
A holdout the human keeps at acceptance, which every later validation
runs. An epic's other holdouts retire when the epic is accepted.
_Avoid_: Regression suite, smoke test, golden test

### Acceptance specs

**Acceptance spec**:
An executable example, in the words of the app's users, of one thing the
app does. It runs against the real app and fails until the app does it.
The human approves each one in planning, builders read and run them but
never change them, and they stay with the app after the epic is accepted.
_Avoid_: Acceptance test, executable spec, Gherkin scenario, feature file,
BDD test

**Protocol driver**:
The code beneath an app's acceptance specs that reaches the running app
through its command line, API or UI and makes the checks the specs ask
for. Writing it fixes the app's interface.
_Avoid_: Harness, adapter, fixture

**Spec task**:
The task that builds what an epic's new acceptance specs need from the
protocol driver, so that they run and fail. Its lap is the only one that
may change the code beneath the acceptance specs, and the tasks that make
them pass wait on it.
_Avoid_: Driver task, harness task

### Keeping the code well built

**Design finding**:
A problem in how the code is built, named by a review or by the human. It
stays a bead outside any epic until planning takes it up or the human
closes it.
_Avoid_: Tech debt, design debt, smell, cleanup item

**Sighting**:
A later pass or planning session meeting a design finding again, recorded
on the finding. A finding's sightings show how often its code is worked on.
_Avoid_: Hit, vote, occurrence

**Design lane**:
The review lane of a pass that judges the design of every module the epic
touched, each read whole rather than as a diff.
_Avoid_: Architecture review, design review

**Prefactoring task**:
A task that reshapes existing code so that a later task in the same epic
is easy, and changes nothing a user sees.
_Avoid_: Preparatory task, enabling task

**Improvement epic**:
An epic that changes how the code is built and nothing a user sees. Only
the human starts one.
_Avoid_: Refactoring epic, cleanup epic, tech-debt epic

**Improvement share**:
The part of recent epics' spend that went to prefactoring tasks and
improvement epics.
_Avoid_: Refactor ratio, investment

### Running the factory

**Host**:
The harness session the human starts and works in. Planning runs in it,
and after a handoff the factory's manager runs in it too.
_Avoid_: Root session, driver, parent

**Heartbeat**:
A file in the jidoka home, one for each epic a manager runs. The manager's
first call writes it, and the lap mod rewrites it every minute while the
host lives. It holds the second of the last beat, so a heartbeat that stops
getting younger shows a stopped factory. An epic handed off with no manager
has none.
_Avoid_: Pulse, ping, keep-alive

**Watcher**:
The background script the manager starts when nothing can run. It exits
when a task is unparked, a task is added, a task merges or a pause is
over, and the manager then goes on. After a failed turn, the lap mod wakes
a host that sits idle with a timer and a prompt.
_Avoid_: Poller, daemon, listener

**Status script**:
The script that shows, from any terminal and with no host, each epic the
factory holds and each task's lap, stage, tries and time against its wall
clock, with the age of the epic's heartbeat. It reads and changes nothing.
_Avoid_: Dashboard, monitor

**Manager**:
The agent in the host that works an epic through its passes. It starts the
workers the scheduler calls for and reports back how each one ended.
_Avoid_: Orchestrator, coordinator, root agent

**Scheduler**:
The script that reads an epic's beads and says what the manager does
next. It applies the dependencies, areas and caps; the manager never does.
_Avoid_: Orchestrator, dispatcher, engine, conductor

**Outcome**:
How a worker's stage ended, as the manager reports it to the scheduler,
from a fixed set. A build ends done, failed or cut off. Done names the
app and the filter of the build's targeted tests. A research brief ends
done with the brief in the scratch folder, an app check ends done with its
report in the scratch folder, and a Spec check ends pass,
send back with its findings, or cannot judge.
_Avoid_: Result, status, verdict

**Try**:
One failed go at a lap's stage, which counts toward the stage's cap. A
failed build, red targeted tests, a filter the targeted tests refuse and
a lap with no commit the epic branch lacks are each a try of the build,
and the third parks the task. A merge worker that fails, leaves its
rebase unfinished, leaves the lap without the epic branch's head or leaves
tests red is a try of the merge, and the second parks the task. A cutoff is
not a try, nor is the epic branch moving under the merge gate, nor is
newer work that calls the merge worker.
_Avoid_: Attempt, retry, strike

**Cap**:
A limit on one lap that parks its task and never stops the factory: three
tries of the build, two tries of the merge worker, two send-backs from the
checks together, and three cutoffs of one stage, apart from the human's own
stop. A stage past its
wall clock, 60 minutes for the build and 30 for any other stage, ends cut
off.
_Avoid_: Budget (that is dollars), limit, quota, timeout

**Brake**:
The stop on new laps that three laps in a row, parked at the same stage
with no merge between, put on an epic. The laps already open run on. It
lifts when the manager files a fix task in the epic. The human's own brake
is the `human` label: on a task it stops new stages on that task, on the
epic it stops new stages on every task, the running stages finish, and
taking the label off lets the factory go on.
_Avoid_: Circuit breaker, halt, freeze

**Worker**:
An agent the manager starts to run one stage, in the host's own harness
or in another harness the host can reach.
_Avoid_: Subagent, child, lane

**Tier**:
A grade of worker that a stage asks for, such as deep or light. A stage
never names a model; each machine's routes say how it runs each tier.
_Avoid_: Class, level, size, model

**Route**:
How one machine runs a tier: a model and effort in the host's own
harness, or in another harness. Each machine keeps its own routes, and a
route that cannot run falls back to the host's harness.
_Avoid_: Provider, backend, adapter

**Account**:
The login a harness runs on at the moment, with its own usage windows or
its own bill: a subscription at home, an API key at work. The human may
change it at any time; jidoka reads it and never chooses it.
_Avoid_: Subscription, plan, login, seat

**Budget**:
The most an epic may spend, in dollars at list price, before it parks.
_Avoid_: Spend cap, limit, quota ("cap" counts tries)

**Reserve**:
The share of an account's usage window that the factory leaves unused.
Past it, the factory starts no new stage on that account.
_Avoid_: Headroom, buffer, threshold

**Area**:
The part of the codebase a task is expected to touch. Handoff names one
for each task, and two laps in the same area never run at the same time.
_Avoid_: Zone, lane, component, scope

**Lap limit**:
The most laps of one epic that run at the same time. The repo settings
hold it, and an epic's factory rules can only set it lower.
_Avoid_: Concurrency, parallelism, max workers

**Slot**:
A number from 1 up that a lap holds while it is open. A new lap takes the
lowest one that no other open lap of the epic holds. The repo settings'
slot use says what a lap does with it, such as pick a port, so two laps
side by side never clash, and so two app checks never share one.
_Avoid_: Port, seat, index

**Scratch folder**:
The `.scratch` folder at the root of a lap's worktree, where the lap's
workers keep files that are not part of the work. The repo's git exclude
file hides it from every git status.
_Avoid_: Temp folder, tmp, workspace

**Lap mod**:
The hooks module in jidoka's plugin that decides every lap worker's tool
call ahead of the host's rules, mode and prompt, so no lap waits on a
permission prompt. It allows a call on the built-in list, the repo's
list or the lap's epic's factory rules, refuses a write outside the lap's worktree, whether by its path or
through a symlink, and denies the rest with a reason. It decides a worker's
first call too, before the worker's agent id is known. The built-in list holds every call the tool marks read-only, a
write inside the worktree, and each app's test command, and the commands a
human added to it for every repo on the machine. The repo's list is the
repo settings' worker commands.
_Avoid_: Permission hook, guard, sandbox, allowlist

**Permission question**:
A question about a call the lap mod denied, when the worker has no other
way round it. It names the denied call and a pattern, the command prefix
that would allow it, and its options are the three lists: the epic's
factory rules, the repo's list and the built-in list. The answer names one
list, the pattern goes onto it, and the next lap's mod allows the call.
_Avoid_: Permission prompt, approval request

### Repos

**Onboarding**:
The one-time step that brings a repo under jidoka on one machine. Its
beads start in stealth mode, and jidoka records what it needs to know
about the repo and its apps.
_Avoid_: Adopt, install, setup, enroll

**Repo settings**:
What onboarding records about one repo on one machine, in jidoka's home and
keyed by the repo's main worktree: its build, the commands lap workers may
run, how a lap tests and uses its slot, the lap limit, each app's build,
run and test commands, and its hand-run tests, the paths of the repo's
glossary and ADRs with whether the repo commits them or keeps them
private, and its rule conflicts. Private glossaries and ADRs stay at their
paths, hidden through the repo's git exclude file, for a shared repo whose
team has not agreed to them. A bench worktree links to the main checkout's
copies, so every worktree shares one copy.
_Avoid_: Repo config, profile, manifest

**Rule conflict**:
A rule the repo documents, in its `CLAUDE.md`, `AGENTS.md`, `CONTRIBUTING.md`
or the like, that overrules one of jidoka's session rules, such as a doc
comment on every public member against jidoka's rule that comments describe
the code. Onboarding lists each one it finds, and the repo settings keep
each one the human confirms, quoting the repo's rule, the file it is written
in and the jidoka rule it overrules. Every session in the repo opens by
saying the repo's rule wins.
_Avoid_: Override, exception, waiver

**App**:
A program or a library that a repo ships, which app checks, holdouts and
acceptance specs reach from outside. People reach a program through its
command line, API or UI; programmers reach a library through its public
API. A repo holds one or more.
_Avoid_: Project, product, target, binary

**Hand-run tests**:
A group of an app's tests that the factory never runs and only the human
does, such as window tests that take keyboard focus or scripts that drive
hardware. The repo settings list each group under `hand_run`, with the text
that leaves it out of the app's test commands, the command that runs it,
and why. Landing ends by listing every group, for the human to run before
trusting the commit.
_Avoid_: Manual tests, skipped tests, excluded tests, slow tests

**Untracer**:
The script, run by the human in a terminal, that takes tracer's files out of
one repo and first copies each original it touches to a backup under jidoka's
home. It keeps the repo's beads, glossaries and ADRs, and the lines of the
rules files that are the repo's own, with any rule of tracer's that the repo
edited kept whole.
_Avoid_: Uninstall, cleanup, migration
