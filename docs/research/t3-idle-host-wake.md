# How a paused factory wakes after T3 ends its idle host

Read on 2026-10-22. The installed app is T3 Code (Nightly)
0.1.2-nightly.20261021.3486 (`CFBundleVersion` in its `Info.plist`). Its
release tag points at commit
[`680152e`](https://github.com/pingdotgg/t3code/tree/680152e27b2a961686389ca69a1557cbb2c55f08),
and every T3 citation below is at that commit. Claude Code is 2.1.308. The
lap mod is on branch `task/lap-mod-hosts` in `lap-kit/`, and the finding that
started this is on the bead Load the lap mod in T3 Code and on the work
machine: T3 ended both idle lap hosts 30 minutes after their last turn, with
SessionEnd reason `other`, and the mod's timers ended with them.

Each claim says whether I read it in source or docs, or saw it in the live
test at the end.

## Short answers

**1. Is there a setting that keeps a Claude session past 30 idle minutes?**
No. The 30 minutes is a constant, `DEFAULT_IDLE_TIMEOUT_MS = 30 * 60 * 1000`,
in `apps/server/src/orchestration-v2/ProviderSessionManager.ts:56`. The
production layer is built with no options, and no setting, environment
variable or UI control reaches it. One thing does hold a session open: live
background work. While the Claude session has a background Bash or Monitor
task, or a running subagent, T3 defers the release for up to four hours of
silence, and any event from the provider restarts that budget.

**2. Can a process outside T3 start a turn in an existing thread at a set
time?** Yes, and none of the ways needs T3 Connect. The simplest is the CLI:
`t3 thread send <thread-id> "<text>"` from any process running as Jeff on the
Mac. It signs itself in through the T3 home directory and calls the server's
MCP endpoint on loopback. Better still, the host can arrange the wake before
it goes idle: a T3 timer task bound to its own thread, made with
`schedule_task`, fires inside the T3 server and needs no outside process at
all. A webhook task also works on loopback, with the token in its URL as the
only credential. Every route needs the T3 server running and the Mac awake.

**3. Does the next turn resume the same Claude Code session?** Yes. T3 keeps
the Claude session id on the thread and, on the first turn after a release,
opens the new `claude` process with `resume` set to that id. The decision is in
`ClaudeAdapterV2.ts:9195-9206` and `:1307-1309`. The live test and older T3
threads in Jeff's data both show the transcript continuing under one session
id after a release. A resume starts a fresh process, so anything a mod kept
only in memory is gone; what it saved to disk or to its atoms is what it gets
back.

## Where the 30 minutes lives

All of this is from source.

`ProviderSessionManager.ts` declares the two limits side by side
([L56-L57](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L56-L57)):

```ts
const DEFAULT_IDLE_TIMEOUT_MS = 30 * 60 * 1000;
const DEFAULT_MAX_IDLE_PIN_MS = 4 * 60 * 60 * 1000;
```

`layerWithOptions` accepts `idleTimeoutMs` and `maxIdlePinMs`
([L229-L232](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L229-L232),
[L401-L402](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L401-L402)),
but the exported layer passes none
([L2524](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L2524)),
and the runtime wires that layer as is
([runtimeLayer.ts:134](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/runtimeLayer.ts#L134)).
Only tests pass options. The settings schema has no idle or keep-alive field
for provider sessions; its `idleClientTtl` is about connected UI clients
([settings.ts:871-881](https://github.com/pingdotgg/t3code/blob/680152e/packages/contracts/src/settings.ts#L871-L881)).
No `T3CODE_*` environment variable touches it. The per-thread **Auto-settle
behavior** menu changes only where the sidebar shows a thread
([thread-sidebar.md:149-162](https://github.com/pingdotgg/t3code/blob/680152e/docs/user/thread-sidebar.md#L149-L162)).

The timer starts when a turn ends. `markIdle` drops the turn from the busy set
and calls `scheduleIdleReleaseInternal`
([L1495](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L1495)),
which sleeps `idleTimeoutMs` and then calls `releaseIfStillIdle`
([L1208-L1241](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L1208-L1241)).
That releases the session with reason `idle_timeout`
([L1109-L1185](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L1109-L1185)):
it closes the session's scope, which ends the `claude` process, and revokes the
MCP credential T3 minted for that session
([L994-L1105](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L994-L1105)).
A Claude session serves one thread only
([ClaudeAdapterV2.ts:336](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L336)),
so this session-level release is the one that ends a Claude host. The design
doc names the "idle-session reaper" as a normal reason a provider process goes
away
([feature-lifecycles.md:271-276](https://github.com/pingdotgg/t3code/blob/680152e/docs/orchestration-v2/feature-lifecycles.md#L271-L276)).

What restarts the 30 minutes: every event the provider sends except live
command output. The event pump returns early for `command_output.delta` and
calls `touchActivity` for the rest
([L1936](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L1936),
[L1963](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L1963)).
A mod timer that writes a file sends no event, which is why the heartbeat did
not keep the lap host alive.

## What holds a session open

From source. When the 30 minutes run out, `releaseIfStillIdle` first asks the
adapter `hasPendingBackgroundWork`. If the answer is yes, it logs
`idle-release-deferred`, sleeps another 30 minutes and asks again, until four
hours have passed since the first deferral
([L1126-L1167](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L1126-L1167)).
Provider activity clears that four-hour clock: "background work that keeps
reporting progress (a long Claude workflow) is never cut off; only work that
went silent for maxIdlePinMs is released"
([L1204-L1207](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L1204-L1207)).

For Claude, pending work means one of three things
([ClaudeAdapterV2.ts:9972-9997](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L9972-L9997)):

- a task on the background roster, which admits only Claude's `local_bash`
  type, the type both a background Bash command and a Monitor run as
  ([L2348-L2351](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L2348-L2351),
  [L2369-L2371](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L2369-L2371));
- a subagent whose status is `running`;
- buffered output from a background task waiting to wake the model.

When a background Bash command ends, Claude Code starts a "wake turn" on the
same process, and T3 routes it to the thread
([L4047-L4049](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L4047-L4049)).
A `local_workflow` does not count, and T3's triage of
[#16697](https://github.com/pingdotgg/t3code/issues/16697) confirms that a
Claude Workflow left alone for hours can lose its session this way.

So while workers run, a factory host is safe: its background subagents pin it.
The trouble is only the pause, when nothing runs. A host could pin itself by
starting a background Bash `sleep` before it goes quiet. The Bash tool in
Claude Code 2.1.308 stops a background command after at most two hours
(default 30 minutes) and wakes the model when it does; a Monitor expires after
at most 30 minutes. I read both limits from the tool descriptions in the 2.1.308
session I ran in, not from Claude Code's source. A five-hour pause would then
need a chain of wake turns, each of which calls the API. I expect that call to
fail during a usage-limit window; the failed turn would leave nothing running,
and 30 minutes later T3 would release the host anyway. I did not test this,
and I would not build on it.

## Starting a turn from outside T3

### `t3 thread send`, from any local process

From docs and source. The user docs describe it for "scripts on the host":
`t3 thread send "$id" "Now fix it"`, which "never interrupts: a busy thread
gets the message as its next turn"
([outside-agents.md:91-111](https://github.com/pingdotgg/t3code/blob/680152e/docs/user/outside-agents.md#L91-L111)).
The CLI reads the running server's origin from `server-runtime.json`, issues
itself a short-lived full-access MCP client session through the server's own
auth store, calls the `/mcp` endpoint with it as a bearer token, and revokes
it when the command ends
([cli/thread.ts:200-234](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/cli/thread.ts#L200-L234)).
`send` calls the `t3_thread_send` tool with `mode: "queue"`
([L614-L646](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/cli/thread.ts#L614-L646)),
which starts an idle thread and queues behind a busy one
([ThreadManagementService.ts:776-780](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ThreadManagementService.ts#L776-L780)).
An archived thread refuses it
([L755-L759](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ThreadManagementService.ts#L755-L759)).

So the credential is file access to `~/.t3/userdata` as the same OS user, and
the transport is loopback HTTP (here `http://127.0.0.1:3773`). No T3 Connect,
no pairing, no agent session. The desktop app starts its server with
`T3CODE_CLI_PATH` set
([DesktopBackendConfiguration.ts:555](https://github.com/pingdotgg/t3code/blob/680152e/apps/desktop/src/backend/DesktopBackendConfiguration.ts#L555)),
and on this Mac the `claude` processes T3 starts inherit
`T3CODE_CLI_PATH=/Users/jeff/.t3/bin/t3`, so a hook can find the CLI without a
hard-coded path. That file is a shell launcher that runs the app's bundled CLI.

The detached process needs the T3 thread id, which T3 does not put in the
environment. The host can read it in any turn with the `t3_thread_configuration`
tool and no arguments, which returns `threadId` for the calling thread
([mcp/toolkits/thread/tools.ts:178-190](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/mcp/toolkits/thread/tools.ts#L178-L190)),
and write it beside its other state.

The host cannot hand its own MCP credential to the detached process: T3
revokes it when it releases the session
([ProviderSessionManager.ts:1066](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/ProviderSessionManager.ts#L1066)).
An outside agent that wants `/mcp` directly signs in through OAuth and a
pairing code
([environment-auth.md:30-52](https://github.com/pingdotgg/t3code/blob/680152e/docs/internals/environment-auth.md#L30-L52)).
The CLI is the short way round.

### A timer task bound to the host's thread

From source and docs. `schedule_task` makes "persistent work in the app
scheduler that runs even when no turn is active", and in the caller's own
project it posts each run into the calling thread by default
(`bindToCurrentThread=true`)
([orchestrator/tools.ts:119-121](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/mcp/toolkits/orchestrator/tools.ts#L119-L121)).
A bound run calls the same `sendToThread` with `mode: "queue"`, following the
thread's current provider
([ScheduledTaskService.ts:826-868](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduledTasks/ScheduledTaskService.ts#L826-L868)).

There are three trigger types and no one-shot
([contracts/scheduledTask.ts:194-221](https://github.com/pingdotgg/t3code/blob/680152e/packages/contracts/src/scheduledTask.ts#L194-L221)):

- `interval`, `everyMs` at least 60 000. The first run is `everyMs` after the
  task is saved, then every `everyMs` after each run
  ([Schedule.ts:17-22](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduledTasks/Schedule.ts#L17-L22)).
- `fixed_time`, a local `HH:MM` on optional weekdays, so at best minute
  precision and once a day
  ([Schedule.ts:24-39](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduledTasks/Schedule.ts#L24-L39)).
- `webhook`, below.

A one-shot wake is therefore an `interval` task whose `everyMs` is the time
until the wake, deleted by the turn it starts (`delete_scheduled_task`). If the
delete never happens it fires again `everyMs` later, which is a retry rather
than a disaster. `fixed_time` is a worse fit: a run more than ten minutes late
is skipped and moved to the next day
([Schedule.ts:68-77](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduledTasks/Schedule.ts#L68-L77),
[ScheduledTaskService.ts:934-979](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduledTasks/ScheduledTaskService.ts#L934-L979)),
while a late `interval` run simply runs.

The scheduler is a loop in the T3 server that wakes every five seconds
([scheduling/Scheduler.ts:54-57](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduling/Scheduler.ts#L54-L57)),
and the scheduled-task source registers on it
([ScheduledTaskService.ts:1036](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduledTasks/ScheduledTaskService.ts#L1036)).
A task persists in the database, survives a server restart, and is deleted
with its thread
([project-settings.md:63-77](https://github.com/pingdotgg/t3code/blob/680152e/docs/user/project-settings.md#L63-L77)).
Nothing about it depends on the host's session or credential.

### A webhook task, on loopback

From source and docs. The webhook route is
`/api/hooks/:hookId/:token`, "unauthenticated by design: the token in the
path, and an optional body signature, are the credential"
([environmentHttp.ts:820-843](https://github.com/pingdotgg/t3code/blob/680152e/packages/contracts/src/environmentHttp.ts#L820-L843)),
and "the URL can also be called directly", not only through the relay
([webhookRoute.ts:72-77](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduledTasks/webhookRoute.ts#L72-L77)).
So a `curl -X POST http://127.0.0.1:3773/api/hooks/<task-id>/<token>` from the
detached process would start a run in the bound thread.

The catch is getting the token. `schedule_task` returns only `webhookUrl`, the
public T3 Connect URL, and returns nothing when there is no managed tunnel
([orchestratorMcp.ts:595-598](https://github.com/pingdotgg/t3code/blob/680152e/packages/contracts/src/orchestratorMcp.ts#L595-L598)).
That URL ends in the same `<task-id>/<token>` as the local path
([ScheduledTaskService.ts:305-318](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/scheduledTasks/ScheduledTaskService.ts#L305-L318)).
Without T3 Connect the token shows only in the settings editor
([project-settings.md:79-86](https://github.com/pingdotgg/t3code/blob/680152e/docs/user/project-settings.md#L79-L86)).
This Mac runs T3's managed `cloudflared` tunnel, so it would get a URL, but the
route buys nothing over `t3 thread send` and adds a standing secret.

### T3's own usage-limit resume

From source and docs. T3 already wakes a thread at a usage-limit reset, under
narrow conditions. When a thread's last run failed with error class
`usage_limit` and a known reset time, and **Auto-resume limited threads** is on
(default off), a sweep on the same five-second scheduler sends "Continue where
you left off." at the reset
([UsageLimitRecoveryWorker.ts:11-72](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/UsageLimitRecoveryWorker.ts#L11-L72),
[settings.ts:1164-1165](https://github.com/pingdotgg/t3code/blob/680152e/packages/contracts/src/settings.ts#L1164-L1165)).
**Resume at reset** does the same for one thread from the UI
([thread-sidebar.md:204-210](https://github.com/pingdotgg/t3code/blob/680152e/docs/user/thread-sidebar.md#L204-L210)).
The Claude adapter classifies 429s and `rate_limit_event` resets as
`usage_limit`
([ClaudeAdapterV2.ts:3105-3196](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L3105-L3196)).
This only fires when the host's own turn failed on the limit. A factory that
pauses on a reserve, or after a worker's failure, while its own turn ends
cleanly, gets nothing from it. It is global, and the text is fixed. It is a
backstop at most.

## The next turn resumes the same Claude session

From source. A Claude provider thread stores the Claude session id as its
`nativeThreadRef`, and every turn reads it from there
([ClaudeAdapterV2.ts:1666-1677](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L1666-L1677)).
Before opening a process, the adapter decides between `sessionId` and `resume`
([L9195-L9206](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L9195-L9206)):

```ts
// openedNativeThreads is per session instance and is lost when the
// provider session is idle-released. A prior turn on this native id
// requires resume; sessionId would fail with "already in use".
const hasPersistedProviderTurn =
  turnInput.nativeThreadHasTurns ?? turnInput.providerTurnOrdinal > 1;
const shouldResume =
  resumeSessionAt !== undefined || openedWithResume || hasPersistedProviderTurn;
```

and `makeClaudeQueryOptions` turns that into `{ resume: nativeThreadId }` or
`{ sessionId: nativeThreadId }`
([L1307-L1309](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts#L1307-L1309)).
Either way the id is the thread's existing Claude session id, and no fork is
requested. The design doc states the rule: on release T3 keeps the provider
thread and its native resume ref, and "on next work, open a new provider
runtime" and resume it
([feature-lifecycles.md:284-303](https://github.com/pingdotgg/t3code/blob/680152e/docs/orchestration-v2/feature-lifecycles.md#L284-L303)).
If the resume fails, T3 builds a replacement provider thread from app context,
which would mean a new Claude session id
([L307-L312](https://github.com/pingdotgg/t3code/blob/680152e/docs/orchestration-v2/feature-lifecycles.md#L307-L312)).

T3 issue [#20219](https://github.com/pingdotgg/t3code/issues/20219) shows the
cost. After a 30-minute idle release, "T3 reopens the session with `resume` on
the next message", in a fresh `claude` process, and Claude Code loses whatever
it held only in memory, there an invoked skill. The lap mod's `restore` reads
its atoms on `session.start`, so it comes back only as far as those atoms
persist across a resume, which this note does not test.

From Jeff's data, before the live test. I matched the Claude session ids that
T3 stores for its threads (`orchestration_v2_projection_provider_threads` in
`~/.t3/userdata/statev2.sqlite`, opened read-only) against transcripts in
`~/.claude/projects/`. Of 120 T3 Claude threads with a transcript, 32 have a
gap of more than 30 minutes between entries. A gap that long means T3 released
the session, unless background work pinned it or the Mac slept. In every one
of the 32 the transcript carries on under a single session id. One example: a
planning thread went quiet at 17:24 UTC, its current provider session was
created at 18:09:41, and its transcript `8416904a-…` continues at 18:09:43 with
the same id.

## T3 must run, and the Mac must stay awake

The scheduler, the CLI's target and the idle reaper all live in the T3 server
process. On this Mac that server is a child of the desktop app (pid 53189 under
53150). A launchd service, `com.t3tools.t3code.service`, is also installed;
while the app owns `~/.t3/userdata` its launcher logs "Another T3 Code server
owns this T3 home" and idles, and it stays idle until restarted rather than
taking over when the app quits
([serviceLauncher.ts:788-791, 815-820](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/serviceLauncher.ts#L788-L820)).
So quitting the app stops every wake route here unless the service is
restarted. `t3 thread send` with no server exits with a "server not running"
error ([cli/thread.ts:212-215](https://github.com/pingdotgg/t3code/blob/680152e/apps/server/src/cli/thread.ts#L212-L215)).
The docs say the same for limit continuations: "The environment must be
running when the reset arrives; it resumes overdue continuations after a
restart."

T3 does nothing to keep the Mac awake. I found no power-save blocker or
`caffeinate` call in the server or desktop source; the desktop only records
suspend and resume for telemetry
([DesktopTelemetryPublisher.ts:186-187](https://github.com/pingdotgg/t3code/blob/680152e/apps/desktop/src/telemetry/DesktopTelemetryPublisher.ts#L186-L187)).
The service doc says to keep the Mac "logged in and awake for unattended
remote access"
([background-service.md:73-76](https://github.com/pingdotgg/t3code/blob/680152e/docs/user/background-service.md#L73-L76)).
While the Mac sleeps nothing runs: not the scheduler, not a detached Python
process, not the mod. After it wakes, an overdue `interval` task runs on the
next five-second tick, because the scheduler compares stored wall-clock times.
A detached process should do the same and compare wall-clock time in a short
loop, not trust one long `sleep`. A T3 Connect relay can hold webhook requests
for up to 24 hours for an offline environment
([project-settings.md:139-146](https://github.com/pingdotgg/t3code/blob/680152e/docs/user/project-settings.md#L139-L146)),
which only helps a sender that is not on the sleeping Mac.

## Live test

Observed in T3 nightly 0.1.2-nightly.20261021.3486 with Claude Code 2.1.308,
on 2026-10-22, times in UTC.

I started two scratch threads in the tracer project with
`t3 thread start ... --provider claudeAgent --model claude-sonnet-5-5 --wait`,
called "Idle wake test A (CLI send)" and "Idle wake test B (T3 timer)". Each
`claude` process started with `--session-id=<id>`: A on `87d1bab9-…`, B on
`b8e3c134-…`. B's first turn called `schedule_task` with
`{type:'interval', everyMs:2160000}` and `bindToCurrentThread` true; T3
returned the task bound to B with `nextRunAt` 19:34:27.

| | Thread A | Thread B |
|---|---|---|
| Last turn ended | about 18:58:19 | about 18:58:29 |
| Provider session `stopped` | 19:28:19.79 | 19:28:29.27 |
| `claude` process | gone by 19:29:39 | gone by 19:29:39 |

Both were released 30 minutes after their last turn, to the second, with no
setting changed.

At 19:29:47 I ran `t3 thread send <A> "... Reply with the single word awake."
--wait --json` from a shell, using no agent credential. It answered `awake` four
seconds later. T3 started a new `claude` process at 19:29:48 with
`--resume=87d1bab9-…`, the provider session row shows a new `createdAt` of
19:29:48, and the transcript `87d1bab9-….jsonl` holds the new user message and
reply under that same session id, with no other id in the file.

The timer half did not run to the end. My own session lost its MCP access
before 19:34 (`parent_not_active`), so to delete the task I sent B a message
with `t3 thread send` at 19:30:25 asking it to call `delete_scheduled_task`.
B resumed with `--resume=b8e3c134-…`, deleted the task, and
`list_scheduled_tasks` then showed none. That repeats the CLI result on a
second thread, but nobody saw a T3 timer wake a released thread; that part
rests on source. Nothing from the test is left scheduled. The two scratch
threads remain in the sidebar and can be archived.

## What I could not settle

- Whether the lap mod's atoms survive a resume. The mod restores from them on
  `session.start`; T3 resumes the same Claude session, but whether Claude Code
  reloads a plugin's atoms for a resumed session is a Claude Code question.
- Whether a native wake turn that fails on a usage limit is recorded as a T3
  run failure with class `usage_limit`, which T3's auto-resume needs.
- Whether Claude Code's two-hour cap on background Bash commands holds in
  every 2.1.x build. I read it from the tool description, not the source.
- What happens to a bound timer task if the user presses Stop on the host
  thread. Stop holds the thread's queue, and a bound run arrives as a queued
  message, so it may wait for a manual resume.

## What this means for the factory

Under T3 the host should not wait on its own clock. Before it goes quiet on a
pause, it should create one `interval` task bound to its own thread, with
`everyMs` set to the wait and a prompt the mod recognizes as a wake. The turn
that task starts deletes the task, runs the scheduler, and arms the next one if
the pause goes on. That puts the timer in the T3 server, which outlives the
host. The live test showed a message sent to a released thread landing in the
same Claude session; that a bound timer delivers its message the same way is
from source, and is the one step worth a short test before building on it.

`t3 thread send` from the detached SessionEnd process is the fallback, and the
one to use for hosts T3 did not start or where `schedule_task` is missing. In
plain Claude Code in a terminal neither exists, and the mod's timers already
work there.

Both need the T3 app open and the Mac awake for the length of the pause.

## Sources

T3 Code, https://github.com/pingdotgg/t3code at commit `680152e`
(tag `v0.1.2-nightly.20261021.3486`): the files linked above. T3 issues
[#16697](https://github.com/pingdotgg/t3code/issues/16697) and
[#20219](https://github.com/pingdotgg/t3code/issues/20219). Local:
`/Applications/T3 Code (Nightly).app/Contents/Info.plist`,
`~/.t3/userdata/server-runtime.json`, `~/.t3/userdata/settings.json`,
`~/.t3/userdata/statev2.sqlite` (read-only), `~/.t3/bin/t3`,
`~/Library/LaunchAgents/com.t3tools.t3code.service.plist`,
`~/.t3/userdata/logs/boot-service.log`, and `~/.claude/projects/`. The lap mod
on branch `task/lap-mod-hosts`, and the bead Load the lap mod in T3 Code and on
the work machine.
