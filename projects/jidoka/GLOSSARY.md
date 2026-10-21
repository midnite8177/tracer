# jidoka

The tool that replaces tracer. The human plans work with it and hands
that work to its factory. The factory runs the work unattended and brings
the result back for the human to accept.

## Language

### Modes of work

**Planning**:
The mode in which the human and an agent turn an idea into epics and
tasks, settling the words and decisions they rest on. It runs from a
wayfinder map down to one stray bug filed into an epic, and ships no code.
_Avoid_: Design, grooming, refinement, intake

**Factory**:
The part of jidoka that works an epic unattended, from its handoff until
the epic reaches the acceptance gate.
_Avoid_: Pipeline, engine, loop

**Acceptance**:
The mode in which the human judges an epic the factory has brought to the
acceptance gate, and either merges it or sends it back with new tasks.
_Avoid_: Sign-off, approval, QA, review

**Bench**:
The mode in which the human and an agent build one bead together, a task
or a stray bug, with the human answering and approving on the spot. Bench
work is never a lap, and it can run while the factory works an epic.
_Avoid_: Pairing, implement, manual mode, attended mode

### Units of work

**Milestone**:
A bead that holds only epics: a container for planning, which the factory
never takes. Milestones wait only on milestones, as epics wait only on
epics and tasks only on tasks.
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

**Lap**:
One task's trip through the factory, from the start of its build to its
merge into the epic branch, retries included. It ends merged, which closes
the task; parked, waiting on the human; blocked, waiting on another task in
the epic; or interrupted, when the factory stopped under it. A task that
did not merge gets a new lap that starts from the work left behind.
_Avoid_: Run, attempt, iteration, loop

**Parked**:
Waiting on the human before the factory goes on. A task or an epic parks
when the factory hits a cap or asks a question, and when the human parks
it to stop new stages starting on it.
_Avoid_: Stuck, on hold, needs-owner, escalated

**Epic branch**:
The branch that collects an epic's work while the factory holds it. Each
lap merges into it, and acceptance merges it into main.
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

**Track**:
How much of a lap a task goes through: the simple track or the full
track. The pass's stages are the same for every task.
_Avoid_: Route, path, class, weight, complexity

**App check**:
The lap stage in which an agent tests the running app from outside, against
the holdouts that name the task, before it reads the diff.
_Avoid_: QA, black-box test, validation

**Spec check**:
The lap stage that asks whether the task's diff does what the task says,
and nothing more.
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

**Test cleanup**:
The first stage of a pass, which deletes the tests the epic added or
changed that add neither confidence nor communication. Each deletion names
the kept test that covers the same behavior.
_Avoid_: Test pruning, test pass

**Validation**:
The last stage of a pass: the full test suite, the epic's holdouts and
every standing holdout, run on the epic branch.
_Avoid_: Test gate, app check, QA

**Discovered work**:
A problem a lap or a pass finds outside the task or diff it is working
on. It is filed as a bead, inside the epic when the epic cannot be
accepted without it, and outside the epic otherwise.
_Avoid_: Side quest, follow-up, tech debt

### Asking the human

**Question**:
A worker's request for a decision from the human, which parks its task or
its epic. It says what the worker found, the options, and the one it
recommends; unparking without an answer takes the recommendation.
_Avoid_: Escalation, prompt, ask, blocker

**Assumption**:
A choice a worker makes inside its task without asking, because it is
cheap to reverse and leaves the task's Demo line as it was. Acceptance
shows the human every one.
_Avoid_: Guess, decision, note

**Notification**:
A message telling the human that the factory waits on them: a task or
the epic parked, only parked tasks left, the epic at the acceptance gate,
or the factory stopped with work left. It points at a bead, and the bead
carries the question; missing a notification loses nothing.
_Avoid_: Alert, ping, push, notice

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

### Running the factory

**Host**:
The harness session the human starts and works in. Planning runs in it,
and after a handoff the factory's manager runs in it too.
_Avoid_: Root session, driver, parent

**Manager**:
The agent in the host that works an epic through its passes. It starts the
workers the scheduler calls for and reports back how each one ended.
_Avoid_: Orchestrator, coordinator, root agent

**Scheduler**:
The script that reads an epic's beads and says what the manager does
next. It applies the dependencies, areas and caps; the manager never does.
_Avoid_: Orchestrator, dispatcher, engine, conductor

**Worker**:
An agent the manager starts to run one stage, in the host's own harness
or in another harness the host can reach.
_Avoid_: Subagent, child, lane

**Route**:
How one machine runs a kind of worker: in the host's own harness, or in
another harness on a named model. Each machine keeps its own routes, and
a route that cannot run falls back to the host's harness.
_Avoid_: Provider, backend, adapter

**Area**:
The part of the codebase a task is expected to touch. Handoff names one
for each task, and two laps in the same area never run at the same time.
_Avoid_: Zone, lane, component, scope
