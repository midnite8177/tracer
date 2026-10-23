# Which harness can carry the local model in T3 Code

Read on 2026-10-20. T3 Code source at two nightly commits:
[`eb7b35a`](https://github.com/pingdotgg/t3code/tree/eb7b35a), which Jeff runs as
0.1.1-nightly.20261018.3331, and [`fe27e8e`](https://github.com/pingdotgg/t3code/tree/fe27e8e),
the newest nightly, 0.1.1-nightly.20261020.3438. Also each harness's docs and
source, T3's issue tracker, and the local omp and T3 config files. This note
builds on `docs/research/other-harnesses.md` on branch `research/other-harnesses`
and does not repeat its general comparison of Pi, nanocoder and OpenCode.

Nothing here was run. I sent no request to Strata, started no T3 thread and
delegated no task, so every statement about whether turns complete comes from
reading source and issue reports.

## Short answer

Strata speaks OpenAI Chat Completions. omp reaches it with
`api: openai-completions`, which posts to `{baseUrl}/chat/completions`. That
rules out Codex, which now accepts only the Responses API, and Claude, which
needs Anthropic Messages, unless Strata also serves one of those. Nothing I
could read says whether it does.

OpenCode through T3's built-in OpenCode driver is the best fit. It talks Chat
Completions through its OpenAI-compatible package, T3 ends its turns on
OpenCode's own end-of-execution events rather than on a model signal, it reads
`SKILL.md` from `.claude/skills` including tracer's nested layout, it reads
`AGENTS.md`, and `delegate_task` can run it as a child. Pointing it at Strata
is one provider block in OpenCode's config, with the context window set by hand.

Upstream Pi through T3's built-in Pi driver comes second. Its config is nearly
a copy of omp's `models.yml`, and T3 waits for the `agent_settled` event that
upstream Pi sends and omp does not. It has two drawbacks. It reads
`.claude/skills` only after a settings entry, and on `openai-completions` T3
loads all of its own roughly 83 tool schemas into every turn.

Generic ACP agents such as Qwen Code and Goose can also take a Chat
Completions endpoint, and `delegate_task` can run them as children. T3 ends an
ACP turn only when the agent answers `session/prompt`, and it has no stall
detection, so each agent's ACP mode has to be trusted on its own. One, Kilo, is
known to hang there.

One risk sits under every option. T3 hands its own MCP tools to each session,
and one of those schemas, `preview_navigate`'s URL pattern, makes llama.cpp's
grammar builder reject the whole request with HTTP 400
([#13068](https://github.com/pingdotgg/t3code/issues/13068), open). If Strata
turns tool schemas into llama.cpp grammars, the first T3 turn will fail before
generation on OpenCode, Pi and ACP alike. Pi should be able to drop the tool
with `--exclude-tools`. OpenCode can avoid T3's tools by connecting to an external
server, at the price of the session not being able to call `delegate_task`
itself. ACP has no switch.

Moving to `fe27e8e` is worth it for this work. It stops delegated results from
wedging a parent with "Insufficient context allowance", shows OpenCode 2 retries
instead of a silent "working", and fixes the ACP model picker for agents that
report models through session state.

## Comparison

| | OpenCode, built-in driver | Upstream Pi, built-in driver | Qwen Code over ACP | Goose over ACP | Codex, built-in driver |
|---|---|---|---|---|---|
| Speaks Chat Completions | Yes | Yes | Yes, the default for `openai` | Yes | No, Responses only |
| T3 ends the turn on | OpenCode idle status (1.x) or `session.execution.*` (2.x) | Pi's `agent_settled`, then an idle probe | the `session/prompt` reply | the `session/prompt` reply | not applicable |
| Known hang reports in T3 | Silent retries before `fe27e8e`; dropped child asks | One parent stuck after delegated notices, cause unknown | None found | None found | not applicable |
| `SKILL.md` | Yes, `.claude/skills` nested | Yes, `.agents/skills`; `.claude/skills` by setting | `.qwen/skills`, `.agents/skills`, one level | `.agents/skills`, also `.claude/skills` | `.agents/skills` |
| `AGENTS.md` | Yes; V2 reads nothing else | Yes, `CLAUDE.md` as fallback | Yes, beside `QWEN.md` | Yes, by default | Yes |
| `delegate_task` runs it as a child | Yes | Yes | Yes | Yes | Yes |
| Gets T3's tools, so can delegate itself | Yes, unless on an external server | Yes, all of them every turn | Through T3's stdio bridge; unconfirmed | Through T3's stdio bridge; unconfirmed | Yes |
| Can drop the grammar-breaking tool | Only by losing all T3 tools | By `--exclude-tools`, untested | No | No | not applicable |
| Installed here | No | No | No | No | Yes |

Every row about turns comes from source reading and other people's issue
reports.

## What Strata speaks

`~/.omp/agent/models.yml` defines one provider, `oracle-strata`, with
`baseUrl: http://<strata-host>:8081/v1`, `api: openai-completions`, an `apiKey`
entry whose value I did not read, and one model,
`qwen3.8-flash-next-iq3_s`, with `supportsTools: true`, `contextWindow: 262144`
and `maxTokens: 32768`. `~/.t3/userdata/settings.json` still has a single
provider instance, `pi`, with `binaryPath: omp`.

oh-my-pi's `openai-completions` provider builds its URL as
`${trimmedBaseUrl}/chat/completions`
([openai-completions.ts:889-890](https://github.com/can1357/oh-my-pi/blob/10b9b49/packages/ai/src/providers/openai-completions.ts#L889-L890)).
Upstream Pi's API of the same name calls `client.chat.completions.create`
([openai-completions.ts:376](https://github.com/earendil-works/pi/blob/bdd9f03/packages/ai/src/api/openai-completions.ts#L376)).
So the confirmed API is `POST /v1/chat/completions` with OpenAI-style tool calls.

One omp session file from 2026-10-19, under
`~/.omp/agent/sessions/-Projects-Volition/`, records 48 assistant replies from
`oracle-strata` over `openai-completions`: 46 ended in tool calls, 2 in `stop`,
none in an error. Strata does answer tool calls. That session contains no T3
tool names, so it says nothing about how Strata handles T3's schemas.

I could not confirm whether Strata also serves `/v1/responses` or
`/v1/messages`, whether it checks the API key, or whether it builds tool-call
grammars from JSON Schema.

## T3 Code's side, for every candidate

**How tools reach a session.** Before T3 opens a provider session it mints an
MCP credential for it, and each driver hands the `t3-code` server to its agent
([orchestrator-mcp-server.md](https://github.com/pingdotgg/t3code/blob/eb7b35a/docs/orchestration-v2/orchestrator-mcp-server.md)).
OpenCode gets it through `mcp.add`, and only on a server T3 started itself
([adapter.ts:961-975](https://github.com/pingdotgg/t3code/blob/eb7b35a/packages/provider-opencode/src/server/adapter.ts#L961-L975),
[v2/adapter.ts:3097-3101](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/provider-opencode/src/server/v2/adapter.ts#L3097-L3101)).
Pi gets it through an extension T3 writes and passes with `--extension`. Every
ACP session gets a stdio server, `t3 acp-mcp-bridge`, because "codex-acp 1.2.0
and pi-acp both drop" HTTP servers
([provider-acp adapter.ts:543-578](https://github.com/pingdotgg/t3code/blob/eb7b35a/packages/provider-acp/src/server/adapter.ts#L543-L578)).
The ACP instance settings have no field to turn that off
([settings.ts](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/provider-acp-registry/src/settings.ts)).

**Which providers can be children.** `delegate_task` takes
`target.providerInstanceId` and `target.model` and runs on any instance with a
V2 orchestration adapter: "Codex, Claude Agent SDK, Cursor Agent SDK, Grok,
generic registry agents over ACP, OpenCode, OpenCode 2, Pi, Antigravity"
([orchestrator-mcp-server.md](https://github.com/pingdotgg/t3code/blob/eb7b35a/docs/orchestration-v2/orchestrator-mcp-server.md)).
A Local ACP command uses the same registry driver, which builds that adapter
([provider-acp-registry driver.ts:501](https://github.com/pingdotgg/t3code/blob/eb7b35a/packages/provider-acp-registry/src/server/driver.ts#L501)).
`orchestrator_capabilities` lists which instances can take a child.

**The grammar failure.** In
[#13068](https://github.com/pingdotgg/t3code/issues/13068) an OpenCode thread
on a custom OpenAI-compatible provider backed by llama.cpp fails with
`Failed to initialize samplers: failed to parse grammar` while `opencode run`
works with the same model. The maintainer triage says T3 registers its own
MCP server on locally started OpenCode servers and suggests an external server
URL as the A/B test. A comment from 2026-10-20 narrows it down. Through
DeepSeek Harness over generic ACP, a third-party llama.cpp fork rejected `\S`
in the grammar built from `mcp__t3-code__preview_navigate`. A one-tool request
failed with the pattern `^\S[\s\S]*\S$|^\S$|^$` and succeeded without it. The
commenter did not test current upstream llama.cpp. The pattern
comes from `Schema.isTrimmed()` on preview URLs, which is still there at
`fe27e8e`
([previewAutomation.ts:15](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/contracts/src/previewAutomation.ts#L15)).
Whether this hits Strata depends on Strata's software, which I cannot see. The
cheapest check is the first T3 turn on any candidate while watching Strata's
own log for that message.

**Two factory traps that do not depend on the harness.** A `delegate_task` with
`mode: "wait"` dies after about five minutes when the parent's MCP client is
Node's `fetch`, and returns no `taskId`
([#11168](https://github.com/pingdotgg/t3code/issues/11168), open). A slow local
child makes that likely, so poll with `mode: "async"` and `task_status`. When
T3 did not know a parent's context window, it assumed 128k, and once a
delegated result arrived every turn on that parent failed
([#16147](https://github.com/pingdotgg/t3code/issues/16147)). PR
[#22117](https://github.com/pingdotgg/t3code/pull/22117), in `fe27e8e` but not
`eb7b35a`, delivers results as a queued message instead of a history handoff,
which removes that trigger.

## OpenCode, built-in driver

**Turns.** The 1.x adapter finalizes a turn when OpenCode reports the session
idle, through a `session.status` or `session.idle` event or a status poll
([adapter.ts:2135-2160, 2596-2628](https://github.com/pingdotgg/t3code/blob/eb7b35a/packages/provider-opencode/src/server/adapter.ts#L2135-L2160)).
The 2.x adapter ends it on `session.execution.succeeded`, `failed` or
`interrupted`
([v2/adapter.ts:2179-2197](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/provider-opencode/src/server/v2/adapter.ts#L2179-L2197)).
Both are OpenCode's own lifecycle, so the model's stop reason does not decide
when the turn ends.

The reports I found are about turns that end badly or look stuck, not ones
that never end:

- While OpenCode 2 waits to retry a model request, T3 at `eb7b35a` drops the
  `session.retry.scheduled` event and the turn looks like ordinary work
  ([#15581](https://github.com/pingdotgg/t3code/issues/15581)). PR
  [#15672](https://github.com/pingdotgg/t3code/pull/15672) fixes that in
  `fe27e8e`. Line 2174 of the 2.x adapter now handles the event.
- A dropped connection to a self-hosted gateway ends every in-flight turn as
  failed, and re-sending works. The maintainers left retries to OpenCode
  ([#20121](https://github.com/pingdotgg/t3code/issues/20121)).
- When an OpenCode-native subagent asks for permission and T3 cannot route the
  request, T3 gives up after about five seconds and the subagent waits forever
  ([#16846](https://github.com/pingdotgg/t3code/issues/16846), open). This
  concerns OpenCode's own subagents, not `delegate_task` children.

**Skills and context files.** As the earlier note found, OpenCode reads
`SKILL.md` from `.claude/skills`, `.agents/skills` and `.opencode/skills`,
nested, in both V1 and V2. V1 reads `AGENTS.md` and falls back to `CLAUDE.md`;
V2 reads only `AGENTS.md`. This repo has `CLAUDE.md` at its root and no
`AGENTS.md`, so OpenCode 2 would see no project instructions here. T3 lists
OpenCode's skills through `opencode debug skill`.

**Delegation.** A child on OpenCode works on either version. With a server
T3 starts, the session also gets T3's tools and can call `delegate_task`. With
**Server URL** set, T3 skips its tools, which also keeps the grammar-breaking
schema away from Strata.

**Pointing it at Strata.** OpenCode is not installed here. T3 needs 1.14.19 or
newer and supports 2.0.18 or newer
([providers-opencode.md](https://github.com/pingdotgg/t3code/blob/eb7b35a/docs/user/providers-opencode.md)).
For OpenCode 2 the V2 docs put a provider in `opencode.jsonc` under
`providers`, with the `@opencode/ai/providers/openai-compatible` package, the
endpoint in `settings.baseURL`, and `limit` and `capabilities` per model
([V2 providers](https://opencode.ai/v2/docs/providers),
[V2 models](https://opencode.ai/v2/docs/models)). That package routes through
`OpenAICompatibleChat`
([openai-compatible.ts](https://github.com/anomalyco/opencode/blob/86a0950/packages/ai/src/providers/openai-compatible.ts)).
Assembled from those pages and untested:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "providers": {
    "strata": {
      "name": "Strata",
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": {
        "baseURL": "http://<strata-host>:8081/v1",
        "apiKey": "{env:STRATA_API_KEY}"
      },
      "models": {
        "qwen3.8-flash-next-iq3_s": {
          "name": "Qwen 3.8 Flash Next (Strata)",
          "capabilities": { "tools": true, "input": ["text"], "output": ["text"] },
          "limit": { "context": 262144, "output": 32768 }
        }
      }
    }
  }
}
```

OpenCode 1.x uses `provider`, `"npm": "@ai-sdk/openai-compatible"`, which the
V1 docs tie to `/v1/chat/completions`, and `options.baseURL`
([V1 providers](https://github.com/anomalyco/opencode/blob/86a0950/packages/web/src/content/docs/providers.mdx)).
Set `limit.context` either way. T3's 2.x adapter takes the window from
OpenCode's model list, `limit.input ?? limit.context`
([v2/adapter.ts:2773](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/provider-opencode/src/server/v2/adapter.ts#L2773)),
and an unknown window is what wedged the thread in #16147. I did not find the
same lookup in the 1.x adapter.

After the config is in place, enable OpenCode in **Settings > Providers** and
refresh it. The model then shows as `strata/qwen3.8-flash-next-iq3_s`, and a
parent can target it with that model and the OpenCode instance id.

## Upstream Pi, built-in driver

**Turns.** T3 finishes a Pi turn when Pi emits `agent_settled` and an idle
probe confirms nothing is streaming, compacting or queued
([adapter.ts:1911-1930](https://github.com/pingdotgg/t3code/blob/eb7b35a/packages/provider-pi/src/server/adapter.ts#L1911-L1930)).
Pi's RPC docs tell clients to wait for exactly that event
([rpc.md](https://github.com/earendil-works/pi/blob/bdd9f03/packages/coding-agent/docs/rpc.md)),
and T3 requires Pi 0.80.5, the first package with it
([status.ts:62-65](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/provider-pi/src/server/status.ts#L62-L65)).
omp never finished because it sends `session_settled` instead. With upstream
Pi that cause goes away.

One open report remains. A Pi 1.2.0 parent with eight async children stayed
`running` for half an hour after Pi wrote its final message, and the logs that
would show whether `agent_settled` arrived were gone
([#19983](https://github.com/pingdotgg/t3code/issues/19983)). The reporter of
[#16846](https://github.com/pingdotgg/t3code/issues/16846) withdrew a claim
that the settle probe never re-arms.

**Skills and context files.** Pi reads `SKILL.md` from `.pi/skills` and
`.agents/skills`, the latter walking up to the repository root, and from
`~/.pi/agent/skills` and `~/.agents/skills`
([skills.md](https://github.com/earendil-works/pi/blob/bdd9f03/packages/coding-agent/docs/skills.md)).
It does not scan `.claude/skills`. A `skills` path in settings adds it, and the
earlier note found that discovery is recursive, so the nested layout would load.
Project skills load only after project trust. T3 passes `--approve` through
from the launch arguments, or the trust can be granted once in a terminal `pi`
session. Pi reads `AGENTS.md`, or `CLAUDE.md` in a directory without one.

**Delegation and the tool load.** Pi can be a child, and through T3's extension
it can call `delegate_task`. On `openai-completions` models the extension
activates every T3 tool on every turn
([mcpExtensionSource.ts:432](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/provider-pi/src/server/mcpExtensionSource.ts#L432),
the same line at `eb7b35a`). PR
[#18643](https://github.com/pingdotgg/t3code/pull/18643) did this on purpose
because some gateways silently drop calls to tools the request did not declare.
[#19190](https://github.com/pingdotgg/t3code/issues/19190), open, measured
83 T3 tools and about 26k tokens of schema, and a one-line prompt grew from
4,591 to 32,125 prompt tokens. That load includes `preview_navigate`. Pi is
the one candidate where it can be cut. T3 passes `--tools` and
`--exclude-tools` from the instance's launch arguments through to Pi
([mcpInjection.ts](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/provider-pi/src/server/mcpInjection.ts)),
and #18643 says Pi applies them to that loadout. I have not seen that work.

**Pointing it at Strata.** Pi is not installed here. Its `models.json` takes
the same shape omp's file has
([models-configuration.md](https://github.com/earendil-works/pi/blob/bdd9f03/packages/coding-agent/docs/models-configuration.md)):

```json
{
  "providers": {
    "strata": {
      "baseUrl": "http://<strata-host>:8081/v1",
      "api": "openai-completions",
      "apiKey": "$STRATA_API_KEY",
      "models": [
        {
          "id": "qwen3.8-flash-next-iq3_s",
          "name": "Qwen 3.8 Flash Next (Strata)",
          "contextWindow": 262144,
          "maxTokens": 32768
        }
      ]
    }
  }
}
```

Then set the T3 Pi instance's binary path back to `pi`, or add a second
instance, and refresh. T3's launch arguments accept `--provider strata --model
qwen3.8-flash-next-iq3_s` as a pair
([providers-pi.md](https://github.com/pingdotgg/t3code/blob/eb7b35a/docs/user/providers-pi.md)).

## Generic ACP agents

**Turns.** T3 finalizes an ACP turn when the agent answers `session/prompt`,
as completed, cancelled or failed
([provider-acp adapter.ts:6664-6703](https://github.com/pingdotgg/t3code/blob/eb7b35a/packages/provider-acp/src/server/adapter.ts#L6664-L6703)).
That is the ACP contract, and it puts the whole question on the agent. Kilo's
ACP mode never answers it, and a reporter reproduced that with no T3 involved
([#19877](https://github.com/pingdotgg/t3code/issues/19877), open). T3 shows
such a turn as running indefinitely. PR
[#21616](https://github.com/pingdotgg/t3code/pull/21616), in `fe27e8e`, lets an
agent's turn settle on native idle, but only flavors that opt in get it, and
only Claude does.

**Models.** At `eb7b35a` an agent that reports its models through ACP session
model state shows only "Default" in the picker; PR
[#19519](https://github.com/pingdotgg/t3code/pull/19519) fixes that in
`fe27e8e`. On the older build, add the model id under **Custom models**.

**Tools.** Every ACP session gets T3's tools through the stdio bridge, with no
way to opt out, and the #13068 comment shows them reaching a llama.cpp fork
this way. Whether a given agent passes stdio MCP servers on to its model is
the agent's business. I confirmed it for none of them.

The registry at
[`8194574`](https://github.com/agentclientprotocol/registry/tree/8194574)
lists 43 agents. I read the ones below.

- **Qwen Code** (registry `qwen-code` 0.25.3, or `qwen --acp` as a Local ACP
  command). The `openai` auth type "defaults to Chat Completions", and local
  servers go under `modelProviders.openai` with `id`, `baseUrl` and `envKey`;
  the docs show `http://localhost` base URLs
  ([model-providers.md](https://github.com/QwenLM/qwen-code/blob/82bd240/docs/users/configuration/model-providers.md)).
  Skills come from `.qwen/skills` and `.agents/skills` under the project root
  and home, plus configured custom user folders, in a fixed
  `<name>/SKILL.md` layout
  ([storage.ts:17](https://github.com/QwenLM/qwen-code/blob/82bd240/packages/core/src/config/storage.ts#L17),
  [skill-manager.ts](https://github.com/QwenLM/qwen-code/blob/82bd240/packages/core/src/skills/skill-manager.ts)).
  Tracer's layout would need `.claude/skills/tracer/skills` added as a custom
  folder. It reads `AGENTS.md` beside `QWEN.md`
  ([memory.md](https://github.com/QwenLM/qwen-code/blob/82bd240/docs/users/features/memory.md)).
- **Goose** (registry `goose` 1.55.0, or `goose acp`). Custom providers can use
  the "OpenAI Compatible" format
  ([providers.md](https://github.com/block/goose/blob/9920efa/documentation/docs/getting-started/providers.md)),
  and the OpenAI engine's default path is `v1/chat/completions`
  ([openai_def.rs](https://github.com/block/goose/blob/9920efa/crates/goose/src/providers/openai_def.rs)).
  Skills come from `.agents/skills`, and for compatibility from `.claude/skills`
  and `~/.claude/skills`
  ([using-skills.md](https://github.com/block/goose/blob/9920efa/documentation/docs/guides/context-engineering/using-skills.md));
  whether nested folders load is unconfirmed. It reads `AGENTS.md` and
  `.goosehints` by default
  ([using-goosehints.md](https://github.com/block/goose/blob/9920efa/documentation/docs/guides/context-engineering/using-goosehints.md)).
- **DeepSeek Harness** (`dsh --profile <name> acp`, the Local ACP example in
  [providers-acp.md](https://github.com/pingdotgg/t3code/blob/eb7b35a/docs/user/providers-acp.md)).
  Its "Custom model API" takes a base URL and the protocol
  `openai-completions`
  ([providers.md](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/user/guide/providers.md)).
  The #13068 commenter ran it against a local Qwen model on a llama.cpp fork. I could
  not find where it reads skills or `AGENTS.md` from.
- **pi-acp** (registry 0.0.34) wraps upstream Pi. Its README says MCP servers
  "are accepted in ACP params and stored in session state, but not wired
  through to pi"
  ([README](https://github.com/svkozak/pi-acp/blob/main/README.md)), so a
  pi-acp session can be a child but cannot call `delegate_task`. The built-in
  Pi driver does more.
- **OpenCode over ACP** (registry `opencode` 1.19.3, the V1 line). T3's
  built-in driver already covers V1 and V2 with OpenCode-specific handling,
  such as its retry events, so I see no reason to choose this route.
- **Cline** reads `.claude/skills`, `.agents/skills` and `AGENTS.md`
  ([paths.ts](https://github.com/cline/cline/blob/d553858/sdk/packages/shared/src/storage/paths.ts)),
  but it has open T3 reports of sessions failing to open
  ([#17072](https://github.com/pingdotgg/t3code/issues/17072)). I did not check
  its custom endpoint settings.

nanocoder, from the earlier note, does not read `SKILL.md`. `omp acp` is left
out because Jeff is moving off omp.

## Ruled out by the wire format

**Codex.** Codex now fails to load a config with `wire_api = "chat"`. Its error
says the value "is no longer supported" and tells the user to set
`wire_api = "responses"`
([model-provider-info lib.rs:100, 122-131](https://github.com/openai/codex/blob/6fb1c39/codex-rs/model-provider-info/src/lib.rs#L100)).
T3's Codex driver itself runs custom model providers, and users report
OpenAI-compatible proxies on it in
[#16147](https://github.com/pingdotgg/t3code/issues/16147) and
[#20075](https://github.com/pingdotgg/t3code/issues/20075). Codex qualifies
only if Strata also serves `/v1/responses`, which is unconfirmed.

**Claude.** T3's Claude driver reads `ANTHROPIC_BASE_URL`
([ClaudeProvider.ts:628](https://github.com/pingdotgg/t3code/blob/fe27e8e/apps/server/src/provider/ClaudeProvider.ts#L628)),
so it needs an Anthropic Messages endpoint, also unconfirmed for Strata.

**Cursor, Grok Build, Antigravity and Muse Code** sign in to their vendors'
accounts ([install.md](https://github.com/pingdotgg/t3code/blob/eb7b35a/docs/user/install.md)).
Cursor's settings keep an `apiEndpoint` field only for V1 compatibility, hidden,
and the V2 SDK ignores it
([settings.ts](https://github.com/pingdotgg/t3code/blob/fe27e8e/packages/provider-cursor/src/settings.ts)).

## What changes between `eb7b35a` and `fe27e8e`

720 commits separate the two. These matter here:

- [#22117](https://github.com/pingdotgg/t3code/pull/22117) delivers delegated
  results without the history handoff that failed with "Insufficient context
  allowance".
- [#15672](https://github.com/pingdotgg/t3code/pull/15672) shows OpenCode 2
  retries instead of a silent running turn.
- [#20037](https://github.com/pingdotgg/t3code/pull/20037) ends a `delegate_task`
  wait when the child has a pending approval.
- [#19519](https://github.com/pingdotgg/t3code/pull/19519),
  [#19567](https://github.com/pingdotgg/t3code/pull/19567) and
  [#19699](https://github.com/pingdotgg/t3code/pull/19699) fix ACP model
  discovery and selection and explain rejected picks.
- [#21614](https://github.com/pingdotgg/t3code/pull/21614) keeps errors that an
  ACP agent reports in its idle state, and
  [#21053](https://github.com/pingdotgg/t3code/pull/21053) re-injects T3's
  instructions into ACP sessions after compaction.
- [#21979](https://github.com/pingdotgg/t3code/pull/21979) stops a failed
  OpenCode background subagent from pinning its thread.
- [#21511](https://github.com/pingdotgg/t3code/pull/21511) and
  [#20521](https://github.com/pingdotgg/t3code/pull/20521) fix Pi session
  launch, fork and revert.

Neither the Pi tool load (#19190) nor the grammar failure (#13068) changes. The
Pi adapter diff is mostly tracing refactors.

## Unconfirmed, or resting on source reading alone

- Whether any candidate's turns complete against Strata. I ran none, and the
  table rests on T3 source and on issue reports from other setups.
- Which APIs besides Chat Completions Strata serves, whether it checks the API
  key, and whether it hits the #13068 grammar failure.
- Whether Qwen Code, Goose or DeepSeek Harness pass T3's stdio MCP bridge
  through to the model, and so whether they can call `delegate_task`.
- Whether those agents' ACP modes answer `session/prompt` reliably. None has a
  T3 report either way.
- Whether `--exclude-tools` on the Pi instance removes T3 tools from the request
  as #18643 describes.
- Whether T3's OpenCode 1.x adapter reads a custom model's `limit.context`.
- Where DeepSeek Harness loads skills and context files from, and whether Goose
  loads nested skill folders.
- Whether the OpenCode and Pi config examples above parse as written. They are
  assembled from docs and source.

## Sources read

| Project | Commit or version | Date |
|---|---|---|
| [pingdotgg/t3code](https://github.com/pingdotgg/t3code) | `eb7b35a` and `fe27e8e`, full trees; issues and PRs linked above | 2026-10-20 |
| [can1357/oh-my-pi](https://github.com/can1357/oh-my-pi) | `main` at `10b9b49`; installed `omp` config and sessions | 2026-10-20 |
| [earendil-works/pi](https://github.com/earendil-works/pi) | `main` at `bdd9f03` | 2026-10-20 |
| [anomalyco/opencode](https://github.com/anomalyco/opencode) | `dev` at `86a0950`; opencode.ai V2 docs | 2026-10-20 |
| [openai/codex](https://github.com/openai/codex) | `main` at `6fb1c39` | 2026-10-20 |
| [agentclientprotocol/registry](https://github.com/agentclientprotocol/registry) | `main` at `8194574` | 2026-10-20 |
| [QwenLM/qwen-code](https://github.com/QwenLM/qwen-code) | `main` at `82bd240` | 2026-10-20 |
| [block/goose](https://github.com/block/goose) | `main` at `9920efa` | 2026-10-20 |
| [cline/cline](https://github.com/cline/cline) | `main` at `d553858` | 2026-10-20 |
| [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) | `master`, providers guide | 2026-10-20 |
| [svkozak/pi-acp](https://github.com/svkozak/pi-acp) | `main` README | 2026-10-20 |
