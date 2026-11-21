# 0012 — An Antigravity host's lap workers are T3 threads guarded by a profile hook

ADR 0005 has the lap mod decide every lap worker's tool call, and the lap
mod is a Claude Code mod. An Antigravity host has no lap mod, and the
human's consumer Google plan rules out a jidoka script running headless
`antigravity -p`, under section 6 of Antigravity's Terms. So when
Antigravity hosts, the manager starts every worker as a top-level T3
thread with `t3_thread_launch` in the lap's existing worktree, archives
the thread when the stage ends, and never deletes it, because T3 offers to
delete the worktree with it. A nested child thread was the preferred
shape, but T3 prepares a child's workspace only through `delegate_task`,
and that tool cannot name an existing worktree. A PreToolUse hook in T3's
Antigravity profile applies the lap lists. It loads in every T3
Antigravity session, so it acts only inside a lap worktree and prints
nothing elsewhere, since an empty answer denies the call. ADR 0005's rule
still holds: no lap waits on a prompt, and a denied call reaches the
worker as a tool error and the run goes on. The plugin copy in T3's
profile names its scripts by absolute path in the version's snapshot
under `~/.jidoka/plugins/`. Install may rewrite that copy, but a running
factory keeps its version's scripts, as ADR 0007 requires. The cost is a
thread per stage in the human's sidebar, titled "lap · " so it can be
skipped, and a dependency on T3's tools that Claude Code hosting does not
have.
