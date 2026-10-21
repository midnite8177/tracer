# jidoka

The tool that replaces tracer. The human plans work with it and hands
that work to its factory. The factory runs the work unattended and brings
the result back for the human to accept.

## Language

### Units of work

**Factory**:
The part of jidoka that works an epic unattended, from its handoff until
the human accepts the result.
_Avoid_: Pipeline, engine, loop

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
the task; parked, waiting on the human; or interrupted, when the factory
stopped under it. A parked or interrupted task gets a new lap that starts
from the work left behind.
_Avoid_: Run, attempt, iteration, loop

**Pass**:
One trip of an epic through the factory: laps for its tasks, then the
epic's own stages over all of its work. A pass ends clean, and the epic
goes to the human for acceptance, or it ends with new tasks in the epic,
and the next pass begins.
_Avoid_: Round, cycle, sweep, loop; "pass" for a stage

**Stage**:
One step of a lap or of a pass, such as the build or the review.
_Avoid_: Step, phase, node, pass

### Running the factory

**Host**:
The harness session the human starts and works in. Planning runs in it,
and after a handoff the factory's manager runs in it too.
_Avoid_: Root session, driver, parent

**Manager**:
The agent in the host that works an epic through its passes, starting a
worker for each stage.
_Avoid_: Orchestrator, coordinator, root agent

**Worker**:
An agent the manager starts to run one stage, in the host's own harness
or in another harness the host can reach.
_Avoid_: Subagent, child, lane

**Route**:
How one machine runs a kind of worker: in the host's own harness, or in
another harness on a named model. Each machine keeps its own routes, and
a route that cannot run falls back to the host's harness.
_Avoid_: Provider, backend, adapter
