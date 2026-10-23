# What each harness does at a usage limit or an outage

Research for the wayfinder map "Design new tracer factory workflow", done on 2026-10-20.
Tags such as [C2] point to the [sources](#sources) at the end.

Versions checked:

- Claude Code 2.1.304, installed, and its docs as published on 2026-10-20. A few doc entries
  already describe 2.1.305.
- Agent SDK `@anthropic-ai/claude-agent-sdk` 0.3.305, read from the npm tarball.
- Codex CLI and `@openai/codex-sdk` 0.163.0, with source read at tag `rust-v0.163.0`.
- T3 Code source at `main` commit `fe27e8e`. The installed app is 0.1.1-nightly.20261018.3331,
  two days older than the source I read.

## Short answer

- **No script surface waits out a subscription limit by default.** `claude -p` ends the turn and
  exits 1 [C13][C14]. `codex exec` fails the turn and exits 1 [X5][X9]. Claude Code waits and
  continues on its own only in an interactive session [C4], and a workflow pauses only there too
  [C9]. Claude has one opt-in for scripts: with `CLAUDE_CODE_RETRY_WATCHDOG=1` a `-p` or SDK
  request sleeps until the reset time, and `CLAUDE_CODE_RETRY_WATCHDOG_MAX_WAIT_MS` caps the sleep
  [C3]. Codex has nothing like it.
- **Claude reports the reset time as a number. Codex `exec` reports it only as English text.**
  Claude's stream-json carries a `rate_limit_event` with `status: "rejected"`, `resetsAt` in epoch
  seconds and `rateLimitType` such as `five_hour` or `seven_day` [C11]. `codex exec --json` puts the
  reset into a sentence in local time, `Try again at 3:45 PM.`, with no time zone [X5]. Codex's
  app-server protocol has the number, but `codex exec` and the TypeScript SDK drop it [X10][X17].
- **Telling a limit from other failures is easy in Claude, with traps.** Every failure carries a
  category such as `rate_limit`, `overloaded` or `server_error`, an HTTP status, and for plan
  limits the event above [C7][C11]. The traps: a turn that died on an API error reports
  `subtype: "success"` with `is_error: true` [C11][C13], and two open bugs can lose the evidence
  from stdout [C14][C15]. In `codex exec` the only evidence is a message string, so a script
  matches `You’ve hit your usage limit`, and that apostrophe is U+2019 [X5].
- **At work on API keys there is no window to wait for.** Anthropic rate limits refill
  continuously [A2]. Claude Code retries 429 throttles and 529 overloads, up to 10 times by
  default [C2]. Codex retries in-stream rate limits and 5xx up to 5 times, using the server's
  suggested delay when there is one, and fails at once on an HTTP 429 that carries no
  `retry-after` [X5][X6][X13]. Codex fails at once on exhausted quota [X5]. Claude's watchdog
  fails at once on a spend-limit 429 [C3]; whether plain Claude Code spends its 10 retries on one
  first, I could not confirm.
- **Outages are retried, then fail with exit 1.** One exception matters for a factory. Codex
  0.163.0 ships `unbounded_connection_retries` on by default, so when the connection itself fails,
  a turn waits for the network forever [X7][X14][X19]. Give every Codex lap its own wall clock.
- **Both resume a conversation by id, not a process.** Claude restores history, model and agent,
  but under `-p` not the permission mode, not flags like `--mcp-config`, and not background tasks
  [C5]. Codex reloads history and takes model, cwd, sandbox and approval policy from the command
  that resumes it [X9]. Neither finishes the cut-off turn unless asked. Claude does with
  `CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1`, but skips turns that ended on an API error more than
  six hours ago [C3]. Codex never does; the caller sends a new prompt [X9].
- **T3 Code is a host, not a script harness.** It runs Claude through the Agent SDK and Codex
  through app-server, marks a stopped thread "Limited" with its reset time, and can send
  "Continue where you left off." at the reset [T1][T3]. That auto-resume is off by default and only
  works while its server is running [T1][T6]. It has no command that runs a prompt from a script
  [T9].

## Claude Code at a glance

| Question | `claude -p` and the Agent SDK | Workflow scripts |
| :- | :- | :- |
| Five-hour or weekly window runs out | The turn ends, nothing is retried, the process exits 1 [C13][C14]. The SDK's single-shot `query()` throws `Claude Code returned an error result: <text>` [C12]. Opt-in wait with `CLAUDE_CODE_RETRY_WATCHDOG=1` [C3] | The agent that hit the limit fails. Pause-and-continue exists only in interactive subscription sessions [C9] |
| Is the reset time reported? | Yes. `rate_limit_event.rate_limit_info.resetsAt` in epoch seconds with `rateLimitType` [C11], and the text `· resets 3:45pm` [C2]. Subscription logins only [C10][C11] | Interactive progress line shows it [C9]. A script sees the failed agent |
| Limit versus other error | `rate_limit_event` status `rejected`; assistant `error: "rate_limit"`; result `is_error`, `api_error_status: 429`, `terminal_reason: "api_error"`; text prefixes in `USAGE_LIMIT_ERROR_PREFIXES` [C7][C11][C14] | `agent()` resolves to `null` on an unrecoverable API error, so the script can't tell which error [C9] |
| API key rate limit at work | 429 throttles retried with backoff, 10 attempts by default, each announced by `system/api_retry`; then `API Error: Request rejected (429)` [C1][C2] | Unconfirmed, presumably the same per agent |
| Overload, 5xx, gateway | Retried. 529 backs off from 500 ms to 32 s; `--fallback-model` switches models; a gateway's HTML page shows as `API Error: 502 Bad Gateway`; `x-should-retry: false` stops retries [C2][C3] | Stalled agents restart up to five times [C9] |
| Network down | Dropped connections retried within the budget, then `Unable to connect to API` [C2]. The watchdog raises the budget to 300 retries, about three hours [C3] | Same |
| Exit codes | 0 on success, non-zero on failure, 143 on SIGTERM [C1] | n/a |
| Resume | `--resume <id or .jsonl path>`, `--continue`; SDK `resume`, `continue`, `forkSession` [C1][C6] | Relaunch the same script in the same session, or `claude --resume` the session and ask Claude to relaunch it [C9] |
| What survives | History, model, agent, unexpired scheduled tasks. Not the `-p` permission mode, not `--mcp-config`, `--settings`, `--plugin-dir`, `--fallback-model`, `--add-dir`, not background tasks [C5] | Saved results of completed agents, replayed in start order [C9] |

## Codex at a glance

| Question | `codex exec` | TypeScript SDK | app-server and Python SDK |
| :- | :- | :- | :- |
| Plan window runs out | Turn fails, no retry, exit 1 [X5][X8][X9] | `run()` throws `Error(message)` [X17] | `TurnError` with `codexErrorInfo: "usageLimitExceeded"` [X12] |
| Is the reset time reported? | Only as text, `Try again at 3:45 PM.` in local time [X5] | Same text [X17] | Yes, `resetsAt` epoch seconds per window from `account/rateLimits/read` [X12] |
| Limit versus other error | Match the message text. `error` lines also appear for retries, so only `turn.failed` is final [X10][X11] | Same | `codexErrorInfo` plus `willRetry` [X12] |
| API key rate limit at work | In-stream `rate_limit_exceeded` retried up to 5 times with the server's delay; HTTP 429 retried only with `retry-after`; quota errors fail at once [X5][X6][X15] | Same | Same, with `rateLimitExceeded` or `usageLimitExceeded` [X5] |
| Overload, 5xx, gateway | 5xx retried with backoff, 4 HTTP retries plus 5 turn retries by default; 503 `server_is_overloaded` retried only with `retry-after` [X5][X6][X13] | Same | `serverOverloaded`, `httpConnectionFailed` and others carry `httpStatusCode` [X12] |
| Network down | Waits forever by default, printing `Reconnecting... waiting for network` [X7][X14] | Same | Same |
| Exit codes | 1 when a turn failed or was interrupted, or a non-retrying error arrived [X9] | Throws `Codex Exec exited with code N: <stderr>` [X17] | n/a |
| Resume | `codex exec resume <id>` or `--last`, with a new prompt [X9][X19] | `resumeThread(id)` [X17] | `thread/resume` [X20] |
| What survives | History. Model, cwd, sandbox and approval policy come from the resuming command [X9] | Same | Same, overridable per call [X20] |

## T3 Code at a glance

| Question | Behavior |
| :- | :- |
| What it runs | Claude through `@anthropic-ai/claude-agent-sdk`, Codex through its app-server [T10]. No CLI command runs a prompt [T9] |
| Plan window runs out | Thread fails with class `usage_limit` and a reset time; the UI shows "Limited" [T1][T4][T5][T7] |
| Is the reset time reported? | Yes, stored per thread as `usageLimitResetAt` [T3][T7] |
| What it does next | Offers Resume, Resume at reset, and Snooze until reset. "Auto-resume limited threads" sends "Continue where you left off." after the reset; off by default [T1][T3][T6] |
| Overload, outage | Shows the provider's retries as retry progress; classifies failures as `provider_error` or `transport_error` [T4][T5] |
| Server restart | Cancels runs that were running, then with `continueThreadsAfterServerUpdate`, on by default, can continue the turn on the same native session [T6][T8] |

## Claude Code in detail

### Subscription windows at home

Pro and Max have a five-hour session limit and a weekly limit, shared between claude.ai and
Claude Code; Max adds a separate weekly limit for Fable [C16]. The help article doesn't say when
a window starts, so I treat the reset time the harness reports as the only reliable clock. The
messages read [C2]:

```text
You've hit your session limit · resets 3:45pm
You've hit your weekly limit · resets Mon 12:00am
You've hit your Opus limit · resets 3:45pm
You've hit your Sonnet limit · resets 3:45pm
```

The session and weekly limits cover every model. The Opus and Sonnet limits cover only that
family, so a run on another model keeps going [C2]. A limit hit in the middle of a response can let
Claude Code finish the step in progress, shown as `Usage limit reached · wrapping up` [C16].

In an interactive session, Claude Code waits and continues on its own after the reset. That is
`autoContinueAtUsageLimit`, on by default since 2.1.234 [C4][C17]. It re-arms at most twice in a
row, doesn't start on its own for a reset more than 24 hours away, which can rule out a weekly
limit, and doesn't survive exiting the session [C4].

In `-p` and the SDK there is no wait. A mock reproduction on 2.1.304 shows what stream-json emits,
in this order [C14]:

```text
{"type":"rate_limit_event","rate_limit_info":{"status":"rejected","resetsAt":1792494000,"rateLimitType":"seven_day","overageStatus":"rejected",...}}
{"type":"assistant","error":"rate_limit","api_error":"usage_limit_reached", ... "You've hit your weekly limit · resets 11am (UTC)"}
{"type":"result","api_error":"usage_limit_reached","result":"You've hit your weekly limit · resets 11am (UTC)","terminal_reason":"api_error",...}
```

The process then exits 1. The result's `subtype` is `"success"` with `is_error: true` and
`api_error_status: 429` [C13]. The type comment in `sdk.d.ts` admits this: a `success` result
carries "with is_error true, the error text when the turn ended on an API error" [C11]. The
agent-loop page still says `success` means "Claude finished the task normally" [C8]. Check
`is_error`, never `subtype`.

`api_error: "usage_limit_reached"` is not in the published types; I saw it only in issue reports
[C13][C14]. T3 Code also parses an undeclared `api_error_params.rate_limit_info` on blocked
assistant messages [T4]. Treat both as observed, not promised.

The `rate_limit_event` type [C11]:

- `status`: `allowed`, `allowed_warning` or `rejected`.
- `resetsAt`: epoch seconds.
- `rateLimitType`: `five_hour`, `seven_day`, `seven_day_opus`, `seven_day_sonnet`,
  `seven_day_overage_included` or `overage`.
- `utilization`, plus overage fields such as `overageStatus` and `isUsingOverage`.

The type is documented as "Rate limit information for claude.ai subscription users" [C11]. The
status line's matching `rate_limits` fields exist only for Pro and Max subscribers [C10].

Before a lap starts, a script can ask for the windows. The SDK's
`usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET()` returns `five_hour` and `seven_day`
utilization with `resets_at` as ISO 8601, and `rate_limits_available: false` on API keys [C11].
The name says what it thinks of being relied on.

### The opt-in wait

`CLAUDE_CODE_RETRY_WATCHDOG=1` is meant for "eval harnesses, CI jobs, or remote workers" [C3]. It:

- retries 429 and 529 capacity errors indefinitely;
- backs off up to five minutes between attempts, "or until the limit resets when the response
  carries a rate-limit reset time, so a session that hits a usage limit waits out the remaining
  window";
- fails at once on a 429 that reports a spend limit or exhausted usage credits;
- raises the retry count for other transient errors, such as server errors, timeouts and dropped
  connections, to 300, about three hours of backoff.

`CLAUDE_CODE_RETRY_WATCHDOG_MAX_WAIT_MS` caps each request's wait, since 2.1.295 [C3].
`CLAUDE_CODE_RETRY_WATCHDOG_USAGE_LIMIT_RECHECK_MS` polls for an early lift, but needs 2.1.305,
one release past the installed 2.1.304 [C3]. A weekly limit can be days away, so an uncapped
watchdog can hold a lap's process open for days.

### Telling a limit from other errors

This is the order I would read a `claude -p` run in, given the open bugs:

1. Use `--output-format stream-json --verbose`. With `json` or `text` output, a
   `rate_limit_event` that arrives after the result replaces it, and the run exits 1 with
   `Error: No messages returned from query` even though the turn succeeded [C15].
2. Keep the last `rate_limit_event`. `status: "rejected"` means a plan window, and `resetsAt` says
   when it lifts [C11].
3. Read the assistant message's `error` field. `rate_limit` is a 429 against quota, `overloaded` a
   529, and the rest are `authentication_failed`, `oauth_org_not_allowed`, `account_on_hold`,
   `billing_error`, `invalid_request`, `model_not_found`, `server_error`, `max_output_tokens`,
   `cloud_credential_error` and `unknown` [C7].
4. Read the result: `is_error`, `api_error_status`, and `terminal_reason`, one of
   `blocking_limit`, `api_error`, `model_error`, `prompt_too_long`, `max_turns`, `budget_exhausted`
   and others [C11]. A 429 with a rejected event is a plan window. A 429 without one, on an API
   key, is a rate limit that outlasted the retries.
5. As a text fallback, the SDK exports `USAGE_LIMIT_ERROR_PREFIXES`, marked alpha: `You've hit
   your`, `You've reached your`, `You're out of usage credits` and nine more [C11].
6. If stdout has none of this and the exit code is 1, read the transcript tail. In one long run on
   2.1.303 the process exited 1 with no rejected event, no assistant error and no result; the
   message was only in `~/.claude/projects/<slug>/<session>.jsonl` as an assistant entry with
   `isApiErrorMessage: true` [C14]. The transcript format is internal and changes between versions
   [C5].

Don't run with `ANTHROPIC_LOG=debug`. Its dumps go to stdout and break the JSON lines [C14].

### API keys at work

The Anthropic API returns 429 `rate_limit_error` when a rate limit is hit. Limits are a token
bucket that refills continuously, and the response carries `retry-after` plus
`anthropic-ratelimit-*-reset` headers in RFC 3339 [A1][A2]. Three other cases look different
[A1][A2]:

- **Tier spend cap.** A 429 with no `retry-after` and
  `error.details.error_code: "enforced_spend_limit_reached"`. Usage pauses until 00:00 UTC on the
  first of the next month.
- **A spend limit you set.** A 400 `invalid_request_error` whose message begins `You have reached
  your specified API usage limits`.
- **Overload.** 529 `overloaded_error`, which the API says can hit all users at once.

Claude Code retries "temporary 429 throttles" within `CLAUDE_CODE_MAX_RETRIES`, default 10,
capped at 15 [C2][C3]. Each retry emits a `system/api_retry` event with `attempt`, `max_retries`,
`retry_delay_ms`, `error_status` and the `error` category; `error_status` is `null` when no HTTP
response came back [C1]. When retries run out [C2]:

```text
API Error: Request rejected (429) · this may be a temporary capacity issue. If it persists, check https://status.claude.com.
```

API-key sessions get no `rate_limit_event`, and the usage call reports `rate_limits_available:
false` [C10][C11]. The docs don't say whether ordinary retries wait for `retry-after`, so I can't
confirm it; `retry_delay_ms` on each `api_retry` event shows the delay actually chosen [C1]. A
Claude apps gateway's spend cap returns `spend limit reached (daily; resets 2026-08-09 00:00 UTC)`
with `x-should-retry: false`, and Claude Code doesn't retry it [C2].

### Overload, server errors, gateways and network loss

Claude Code retries these before showing an error [C2]:

- server errors, overloads and timeouts that arrive before any of the response has streamed;
- dropped connections, including one broken by the computer going to sleep;
- a stalled stream, once;
- a request that gets no response headers by the first-byte deadline, once, unless the watchdog is
  set;
- temporary 429 throttles, and `Server is temporarily limiting requests (not your usage limit)`,
  which it recognizes by the missing quota headers.

It does not retry TLS certificate failures, or a failure that arrives after Claude finished a
block of text or a tool call. In that second case it keeps what Claude finished, runs the
completed tool calls, and continues the turn. Under `-p` it also prompts Claude to continue a
cut-off text response, up to three times [C2].

For a 529 the backoff starts at 500 ms and stops at 32 s, both tunable [C2]. With an API key on
Opus, retrying stops at the third 529. A fallback model set with `--fallback-model` takes over
instead of the error [C3][C18]. The final message is `API Error: Repeated 529 Overloaded errors.`,
and a 529 doesn't count against quota [C2].

Messages a script will see [C2]:

```text
API Error: 500 Internal server error. This is a server-side issue, usually temporary — try again in a moment. If it persists, check https://status.claude.com.
API Error: 502 Bad Gateway
API Error: No response from API (waited 3m, then 10m on the retry). If a proxy or gateway on your network holds responses until they complete, raise API_TIMEOUT_MS or CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS to wait longer.
Unable to connect to API. Check your internet connection
```

The 502 form is what a proxy or gateway's HTML error page becomes. `API_TIMEOUT_MS` defaults to
600000 [C2].

Exit codes: 0 on success, non-zero when the run fails, with in-run failures printed as the result
on stdout [C1]. SIGTERM exits 143, leaves the running turn unfinished and records no result for
it; send SIGINT or call `interrupt()` first to end the turn cleanly [C1]. I did not check what
Windows does when the process is killed.

### Resume and what survives

`claude -p --resume <session-id>` continues a session, and the id is found in any project on the
machine. `--resume` also takes the absolute path to the `.jsonl` file. `--continue` picks the most
recent session in the directory [C1]. The SDK has `resume`, `continue`, `forkSession`, and
`persistSession: false` [C6]. Every result carries `session_id`, errors included [C6].

Transcripts live at `~/.claude/projects/<project>/<session-id>.jsonl`. `cleanupPeriodDays`
deletes them after 30 days by default, and `--no-session-persistence` turns them off for one run
[C5].
They are local to the machine. To resume elsewhere, copy the file into any directory under
`~/.claude/projects/` or use a `SessionStore` adapter [C6].

A resumed session gets back [C5]:

- the conversation, from the last compaction's summary onward;
- the model and the agent it ran as;
- an active goal and unexpired session-scoped scheduled tasks;
- an interrupted tool call, marked as cut off. Claude is told to check whether it took effect
  before running it again;
- background subagents, Bash commands and workflows that died with the process, as notes. No turn
  starts from them.

It does not get back [C5]:

- the permission mode, under `-p`. A resumed `-p` run starts in the mode a new `-p` run would, plan
  mode excepted;
- `--mcp-config`, `--settings`, `--plugin-dir`, `--fallback-model` and `--add-dir`. Pass them
  again;
- background Bash and monitor tasks.

Sessions persist the conversation, not the filesystem [C6].

By default the next prompt drives a resumed session, and the cut-off turn stays as it was [C1].
`CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1` continues it instead, sending `CLAUDE_CODE_RESUME_PROMPT`,
default `Continue from where you left off.` [C3]. `CLAUDE_CODE_RESUME_INTERRUPTED_TURN_MAX_AGE_MS`
bounds how stale a turn may be. When it is unset, "some turns resume only within six hours of their
last message, such as one that ended with an API error" [C3]. A lap stopped by a weekly limit and
resumed a day later therefore starts idle and needs an explicit prompt.

### Workflow scripts

A workflow agent that hits a usage limit pauses only when all of these hold: the session is
interactive and signed in with a subscription, `autoContinueAtUsageLimit` is on, the limit resets
within 24 hours, and the run hasn't already waited twice. Otherwise the agent fails, and that
includes every `-p`, SDK and background session [C9].

An `agent()` call resolves to `null` when it hits an unrecoverable API error, so the script sees
`null` and not the reason [C9]. I assume a usage-limit failure counts as one of those; the page
doesn't say. A stalled agent behaves differently. It restarts from the same prompt up to five
times, then fails with `agent stalled on all 6 attempts`, `agent lost its reply on all 6 attempts`
or `agent abandoned after 6 attempts`. Inside `parallel()` or `pipeline()` that failure leaves
`null` in the slot; awaited directly, it ends the run [C9].

Relaunching replays the run in the order agents start [C9]:

- A completed agent returns its saved result, until the first agent whose prompt differs. That one
  and every agent after it run again.
- An agent still running when the run stopped starts over.
- A failed agent runs again, and so does every agent started after it, even completed ones.

So a usage limit in the middle of a fan-out reruns finished work started after the failure.
`Date.now()`, `Math.random()` and a no-argument `new Date()` throw inside the script, which keeps
the replay deterministic [C9].

A run can be resumed within the same session. After the session exits, the saved results stay in
that session's directory under `~/.claude/projects/`; `claude --resume` the session and ask Claude
to relaunch the workflow. A fresh session starts the workflow over, and missing results fail with
`nothing to resume` [C9].

## Codex in detail

### Subscription windows at home

The pricing page gives five-hour windows for Plus and Business, says "Pro plans currently have no
five-hour limit", and says "Weekly limits may also apply" [X2]. A turn already running "will be
able to continue working on that turn, subject to fair use limits", and `/status` in the CLI shows
what is left [X2]. Like Anthropic's, the page doesn't define when a window starts.

The server signals a plan limit as HTTP 429 with error type `usage_limit_reached` and a `resets_at`
in epoch seconds; Codex turns that into `UsageLimitReached` [X6]. Headers named
`x-codex-primary-*` and `x-codex-secondary-*` carry used percent, window minutes and reset time
[X16]. Each window in the resulting snapshot has its own `window_minutes` and `resets_at`, so a
script should read the duration rather than assume which window is weekly [X12].

`UsageLimitReached`, `UsageNotIncluded` and `QuotaExceeded` are never retried [X5]. The turn loop
returns the error at once and records the snapshot [X8]. The message is built in
`UsageLimitReachedError`'s `Display` [X5]:

```text
You’ve hit your usage limit. Visit https://chatgpt.com/settings/usage to purchase more credits or try again at 3:45 PM.
You’ve hit your usage limit. Try again at Oct 21st, 2026 3:45 PM.
You’ve hit your usage limit. Try again later.
You’ve hit your usage limit for <limit name>. Switch to another model now, or try again at 3:45 PM.
Your workspace is out of credits. Add credits to continue.
```

The plan type picks the advice. The time is local, gets a date only when the reset isn't today,
and has no time zone. The apostrophe in `You’ve` is U+2019, so an ASCII `You've` match fails.

### `codex exec`

The JSONL events are `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.*`
and `error` [X1][X17]. `turn.failed` carries `{"error":{"message": ...}}` and `error` carries
`{"message": ...}`, nothing else [X10][X17]. The app-server's `codexErrorInfo` is dropped on the
way out [X10].

An `error` line is not always fatal. The app-server sends each retry as an error notification with
`willRetry: true` [X11], and `exec` writes every error notification as an `error` event without
checking that flag [X10]. Messages like `Reconnecting... 2/5` show up as `error` lines while the
turn carries on. Only `turn.failed` is final.

`exec` exits 1 when it saw a non-retrying error, or a turn that ended failed or interrupted [X9].
Startup failures also exit 1 [X9]. Without `--json`, errors go to stderr as `ERROR: <message>`
[X1][X10]. No rate-limit event reaches `exec`'s output [X10].

### TypeScript SDK

`@openai/codex-sdk` spawns `codex exec --experimental-json` and parses its lines [X17]. `run()`
throws `new Error(turnFailure.message)` on `turn.failed`. A non-zero exit throws `Codex Exec exited
with code N: <stderr>`. `runStreamed()` yields the same events as `exec` [X17]. So it knows no more
than `exec` does.

### App-server and the Python SDK

The Python SDK `openai-codex` drives the app-server over JSON-RPC [X4]. There a failed turn's
`TurnError` has `message`, `codexErrorInfo` and `additionalDetails`, and each error notification
has `willRetry` [X12]. `codexErrorInfo` values include `usageLimitExceeded`, `rateLimitExceeded`,
`serverOverloaded`, `internalServerError`, `unauthorized`, and `httpConnectionFailed`,
`responseStreamConnectionFailed`, `responseStreamDisconnected` and
`responseTooManyFailedAttempts`, the last four with `httpStatusCode` [X12].
`account/rateLimits/read` and the `account/rateLimits/updated` notification give each window's
`usedPercent`, `windowDurationMins` and `resetsAt` [X12].

One catch: plan limits, `QuotaExceeded` and `UsageNotIncluded` all map to `usageLimitExceeded`
[X5]. On an API key, "out of money" and "wait for the window" look alike, and only the message
tells them apart.

The Python SDK's `run()` raises `RuntimeError(turn.error.message)` on a failed turn and drops the
code [X18]; the raw notification stream keeps it. Its `ServerBusyError` and `retry_on_overload`
cover JSON-RPC overload errors, not failed turns [X18].

### API keys at work

Two layers of retry, both per model provider [X3][X13]:

- `request_max_retries`, default 4, retries an HTTP request on 5xx and transport errors with a
  200 ms base delay. It never retries a 429 [X13].
- `stream_max_retries`, default 5, retries a failed turn request at the turn level, and shows
  `Reconnecting... n/5` [X7].

Both values cap at 100 [X13]. `stream_idle_timeout_ms` defaults to 300000 [X3].

How rate limits fall into those layers:

- An in-stream `response.failed` with code `rate_limit_exceeded` or `slow_down` is retried after
  the server's `retry-after`, or after a delay parsed from text like `Please try again in 11.054s`
  [X15][X5].
- An HTTP 429 that isn't a usage or quota error becomes `RetryLimit`. It is retried only when the
  server sent `retry-after`, and fails at once otherwise [X6][X5].
- `insufficient_quota`, `credit_balance_exhausted`, `organization_spend_limit_exceeded`,
  `project_spend_limit_exceeded` and `organization_usage_limit_exceeded` become `Quota exceeded.
  Check your plan and billing details.`, never retried [X6][X5].

### Overload, server errors, gateways and network loss

How `api_bridge.rs` classifies responses [X5][X6]:

- A 503 with code `server_is_overloaded` becomes `Selected model is at capacity. Please try a
  different model.`, retried only when the server sent `retry-after`.
- A 500 becomes `We’re currently experiencing high demand, which may cause temporary errors.`,
  retried with backoff.
- Any other status, which covers a gateway's 502 or 504, becomes `unexpected status <code>:
  <body>` with the URL, `cf-ray` and request id appended. It is retried with backoff.
- A stream that drops before `response.completed` is retried.
- After the WebSocket transport exhausts its retries, Codex falls back to HTTPS and starts the
  count again [X7].

The outlier is a failed connection. `unbounded_connection_retries` is stable and on by default in
0.163.0, described as "Keep active sampling turns alive until a failed network connection
recovers" [X14][X19]. On a `ConnectionFailed` error the turn waits 5 s, doubling to a 60 s
ceiling, prints `Reconnecting... waiting for network`, and never gives up [X7]. A dead network or
an unreachable gateway host therefore hangs `codex exec` instead of failing it.
`--disable unbounded_connection_retries` turns it off for one run [X19]. HTTP errors from a
gateway that answers are still bounded by the retry counts above.

### Resume and what survives

`codex exec resume <SESSION_ID>` takes a UUID or thread name; `--last` picks the newest session
for the current directory, and `--all` drops that filter [X19]. The SDK's `resumeThread(id)` adds
`resume <id>` to the `exec` command line [X17]. The SDK says threads persist in `~/.codex/sessions`
[X17]. 0.163.0 also ships `codex migrate-rollouts`, which moves "legacy local sessions to
paginated thread history" [X19], and I found SQLite files such as `thread_history_1.sqlite` under
`~/.codex`. The storage layout is changing; I did not confirm where a given thread lives.

What a resumed run gets:

- The history, loaded from disk [X9][X20].
- Model, provider, cwd, workspace roots, approval policy and sandbox from the resuming command's
  own configuration, not from the thread [X9]. Pass the same flags the lap started with.
- A new user turn, never the old one. `exec resume` always starts a turn from the prompt argument
  or stdin [X9]. A turn that failed on a usage limit stays failed, and the caller sends "continue"
  or a fuller prompt.

`--ephemeral` turns persistence off [X1], and `exec resume` refuses `--worktree` [X9].

I found no Codex equivalent of Claude's marker for a tool call cut off by a killed process. What
the model sees on resume in that case is unconfirmed.

## T3 Code in detail

T3 Code is a desktop, web and mobile app with a server process, `t3 serve` or the background
`t3 service`. Its CLI commands cover auth, connect, doctor, pair, project, service, start, serve and
trace; none runs a prompt from a script [T9]. It runs Claude through
`@anthropic-ai/claude-agent-sdk` `^0.3.276` and Codex through a JSON-RPC client for `codex
app-server` [T10]. So it inherits each harness's retries and adds a layer of its own.

It sorts provider failures into `usage_limit`, `provider_error`, `transport_error`,
`permission_error`, `validation_error` and `unknown`. Each failure has a `code`, a `retryable` flag
and an optional `resetAt` [T7].

How the Claude adapter classifies [T4]:

- A result with `api_error_status: 429` is `usage_limit`; a 529 is overloaded and retryable.
- An `api_retry` event with status 429 is `usage_limit`; one with a null status is
  `transport_error`.
- The reset time comes from `rate_limit_event.resetsAt` and from the undeclared
  `api_error_params.rate_limit_info` on blocked assistant messages.
- It parses a gateway's 503 that wraps an Anthropic 429 with `(reset after 1h2m3s)`.

How the Codex adapter classifies [T5]:

- `usageLimitExceeded`, `rateLimitExceeded`, or `responseTooManyFailedAttempts` with HTTP 429 is
  `usage_limit`.
- The reset time comes from the account rate-limit snapshot.
- Notifications with `willRetry: true` show as retry progress, not as failures.

What the user sees [T1]: a limited thread shows "Limited" and keeps the provider's explanation.
Resume continues it by hand. Resume at reset schedules a continuation when the provider reported a
reset time. "Auto-resume limited threads" makes that the default. "The environment must be running
when the reset arrives; it resumes overdue continuations after a restart." Stopping, sending a new
message, archiving or settling the thread cancels a pending continuation. Snooze until reset hides
the thread until then.

Underneath, a scheduled sweep looks for failed threads whose last error class is `usage_limit` and
whose reset time is later than the failure. After the reset it dispatches the message `Continue
where you left off.` to the same thread [T3]. `autoResumeLimitedThreads` and
`snoozeLimitedThreads` both default to false [T6].

On startup the server cancels runs that were still running, with the note `Cancelled because the
server restarted before the provider work completed.` [T8]. If `continueThreadsAfterServerUpdate`
is on, which is the default [T6], and the native session can be resumed, it sends `Continue where
you left off.` plus a note about cancelled background work. It allows three chained continuations
within five minutes, then stops [T8]. The graceful path records the continuation before shutdown.
Whether a hard crash meets the gating conditions I did not confirm.

The Limits view pools every Claude and Codex account across environments and shows each window's
reset time [T2]. A thread can move to another signed-in account of the same provider and continue
[T1][T11].

## What this means for the factory

These are my inferences from the facts above, not findings.

- An exit code of 1 means "something failed" in both CLIs. Classify a lap's end from the stream.
- For Claude laps, run `--output-format stream-json --verbose`, keep the last `rate_limit_event`,
  and record `rejected` plus `resetsAt` on the bead as "interrupted until T". Fall back to the
  result's `is_error` and `api_error_status`, then to the transcript tail.
- For Codex laps through `exec`, match `turn.failed` messages starting `You’ve hit your usage
  limit` or `Quota exceeded`. The reset time is only in local-time text. To get a number, drive
  app-server as T3 Code does, or call `account/rateLimits/read` before the next lap.
- Put a wall clock on every Codex lap, or pass `--disable unbounded_connection_retries`.
  Otherwise a network outage looks like a lap that never ends.
- Decide whether a lap waits or ends interrupted. The brief says a lap cut off ends interrupted
  and the next lap resumes. That points away from `CLAUDE_CODE_RETRY_WATCHDOG`, or toward
  setting it with a `CLAUDE_CODE_RETRY_WATCHDOG_MAX_WAIT_MS` short enough that a process doesn't
  outlive the machine's useful uptime.
- Store the session id on the bead when the lap starts: `session_id` from Claude's `system/init`
  [C6], `thread_id` from Codex's `thread.started` [X17]. Resume with the same flags. Send an
  explicit continuation prompt. Claude's automatic one skips a turn that ended on an API error more
  than six hours earlier [C3], and Codex has none.
- At home, a weekly limit can be days away. Even interactive auto-continue won't wait past 24
  hours [C4].

## Unconfirmed

- Whether Claude Code's ordinary 429 retries honor `retry-after`.
- Whether Claude Code without the watchdog retries an Anthropic tier spend-cap 429, which never
  carries `retry-after`, before failing.
- Whether a watchdog wait on a usage limit emits `api_retry` events, and with what
  `retry_delay_ms`.
- Whether `CLAUDE_CODE_RETRY_WATCHDOG` applies to workflow agents in a `-p` run.
- The fields `api_error` and `api_error_params`, seen in issues and in T3 Code's parser but absent
  from `sdk.d.ts` 0.3.305.
- What Claude Code and Codex return when killed on Windows.
- What Codex shows the model on resume for a tool call that a killed process cut off.
- Where Codex 0.163.0 stores a thread: rollout files, SQLite, or both.
- Whether T3 Code's restart continuation fires after a hard crash, as opposed to a graceful
  restart or update.
- When the five-hour and weekly windows start, for either vendor. The help pages don't say.

## Sources

Claude Code and the Agent SDK:

- [C1] Run Claude Code programmatically: <https://code.claude.com/docs/en/headless>
- [C2] Errors: <https://code.claude.com/docs/en/errors>, sections Automatic retries, Tune retry
  behavior, Server errors, Usage limits
- [C3] Environment variables: <https://code.claude.com/docs/en/env-vars>, entries
  `CLAUDE_CODE_MAX_RETRIES`, `CLAUDE_CODE_RETRY_WATCHDOG*`, `CLAUDE_CODE_RESUME_INTERRUPTED_TURN*`
- [C4] Wait for a usage limit to reset:
  <https://code.claude.com/docs/en/interactive-mode#wait-for-a-usage-limit-to-reset>
- [C5] Sessions: <https://code.claude.com/docs/en/sessions>, section What a resumed session
  restores
- [C6] Agent SDK sessions: <https://code.claude.com/docs/en/agent-sdk/sessions>
- [C7] Agent SDK TypeScript reference: <https://code.claude.com/docs/en/agent-sdk/typescript>,
  `SDKAssistantMessageError`, `SDKRateLimitEvent`
- [C8] Agent loop, Handle the result:
  <https://code.claude.com/docs/en/agent-sdk/agent-loop#handle-the-result>
- [C9] Workflows: <https://code.claude.com/docs/en/workflows>, sections Resume after a pause, When
  a run hits your usage limit, When an agent stalls and restarts
- [C10] Status line, rate limit usage:
  <https://code.claude.com/docs/en/statusline#rate-limit-usage>
- [C11] `sdk.d.ts` in `@anthropic-ai/claude-agent-sdk@0.3.305` from `npm pack`: `SDKRateLimitInfo`,
  `SDKAPIRetryMessage`, `SDKAssistantMessageError`, `SDKResultSuccess`, `SDKResultError`,
  `TerminalReason`, `USAGE_LIMIT_ERROR_PREFIXES`,
  `usage_EXPERIMENTAL_MAY_CHANGE_DO_NOT_RELY_ON_THIS_API_YET`
- [C12] `sdk.mjs` in the same package: the error path that throws `Claude Code returned an error
  result:`
- [C13] Issue 103807, Print JSON marks a usage-limit API error as subtype success:
  <https://github.com/anthropics/claude-code/issues/103807>
- [C14] Issue 103820, Print mode exits 1 on a weekly usage limit without the rate_limit_event:
  <https://github.com/anthropics/claude-code/issues/103820>
- [C15] Issue 103253, `claude -p` exits 1 when a `rate_limit_event` arrives after the result:
  <https://github.com/anthropics/claude-code/issues/103253>
- [C16] Using Claude Code with your Pro or Max plan:
  <https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan>
- [C17] Settings reference, `autoContinueAtUsageLimit`:
  <https://code.claude.com/docs/en/settings-reference#autocontinueatusagelimit>
- [C18] `claude --help`, Claude Code 2.1.304, run locally

Anthropic API:

- [A1] Errors: <https://platform.claude.com/docs/en/api/errors>
- [A2] Rate limits: <https://platform.claude.com/docs/en/api/rate-limits>, sections Reaching your
  spend cap, Response headers

Codex, with source files at tag `rust-v0.163.0` of <https://github.com/openai/codex>:

- [X1] Non-interactive mode: <https://learn.chatgpt.com/docs/non-interactive-mode>, redirected
  from <https://developers.openai.com/codex/noninteractive>
- [X2] Pricing: <https://learn.chatgpt.com/docs/pricing>
- [X3] Config reference: <https://learn.chatgpt.com/docs/config-file/config-reference>
- [X4] Codex SDK: <https://learn.chatgpt.com/docs/codex-sdk>
- [X5] `codex-rs/protocol/src/error.rs`: `CodexErrorDetails`, `retry_delay`,
  `to_codex_protocol_error`, `UsageLimitReachedError`
- [X6] `codex-rs/codex-api/src/api_bridge.rs`: HTTP status classification
- [X7] `codex-rs/core/src/responses_retry.rs`: turn-level retries, unbounded connection retries,
  transport fallback
- [X8] `codex-rs/core/src/session/turn.rs`: sampling loop, no retry on `UsageLimitReached`
- [X9] `codex-rs/exec/src/lib.rs`: exit codes, `thread_resume_params_from_config`, resume prompt
  handling
- [X10] `codex-rs/exec/src/event_processor_with_jsonl_output.rs` and
  `event_processor_with_human_output.rs`: what reaches stdout and stderr
- [X11] `codex-rs/app-server/src/bespoke_event_handling.rs`: `StreamError` sent with
  `will_retry: true`
- [X12] `codex-rs/app-server-protocol/src/protocol/v2/`: `shared.rs` (`CodexErrorInfo`),
  `notification.rs` (`ErrorNotification`), `thread_data.rs` (`TurnError`), `account.rs`
  (`RateLimitSnapshot`, `RateLimitWindow`)
- [X13] `codex-rs/model-provider-info/src/lib.rs`: retry defaults and caps
- [X14] `codex-rs/features/src/lib.rs`: `unbounded_connection_retries`, stable, default on
- [X15] `codex-rs/codex-api/src/sse/responses_error.rs`: in-stream rate limit errors
- [X16] `codex-rs/codex-api/src/rate_limits.rs`: `x-codex-*` rate limit headers
- [X17] `@openai/codex-sdk@0.163.0` from `npm pack`: `dist/index.d.ts`, `dist/index.js`
- [X18] `sdk/python/src/openai_codex/_run.py`, `sdk/python/src/openai_codex/errors.py`,
  `sdk/python/examples/10_error_handling_and_retry/sync.py`
- [X19] Codex CLI 0.163.0 run locally: `codex exec --help`, `codex exec resume --help`,
  `codex features list`, `codex migrate-rollouts --help`
- [X20] `codex-rs/app-server-protocol/src/protocol/v2/thread.rs`: `ThreadResumeParams`

T3 Code, at commit `fe27e8e3dc12dcbb108e9a28fd9b8cb65f34ae92` of
<https://github.com/pingdotgg/t3code>:

- [T1] `docs/user/thread-sidebar.md`, section Inspect agent work
- [T2] `docs/user/usage.md`, section Track subscription limits
- [T3] `apps/server/src/orchestration-v2/UsageLimitRecoveryWorker.ts`
- [T4] `apps/server/src/orchestration-v2/Adapters/ClaudeAdapterV2.ts`: `providerFailureFromResult`,
  `providerFailureFromApiRetry`, `isClaudeBlockedAssistantRateLimit`
- [T5] `apps/server/src/orchestration-v2/Adapters/CodexAdapterV2.ts`: `codexUsageLimitError`
- [T6] `packages/contracts/src/settings.ts`: `autoResumeLimitedThreads`, `snoozeLimitedThreads`,
  `continueThreadsAfterServerUpdate` defaults
- [T7] `packages/contracts/src/orchestrationV2.ts`: `OrchestrationV2ProviderFailureClass`,
  `OrchestrationV2ProviderFailure`
- [T8] `apps/server/src/orchestration-v2/RestartContinuation.ts` and
  `ProviderRuntimeRecoveryService.ts`
- [T9] `apps/server/src/cli/`: the CLI's command list
- [T10] `apps/server/package.json` and `apps/server/src/provider/CodexProvider.ts`
- [T11] `docs/user/providers-codex.md`, sections on multiple accounts
