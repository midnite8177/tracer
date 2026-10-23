# Farley's ATDD skill, and mutation testing for C#, C++ and Python

Research for jidoka, done on 2026-10-21. I checked Farley's video
description and its link, CD.Training's course pages and GitHub, and the
repos, docs and PyPI entries of seven mutation tools. Tags such as [F4]
point to the [sources](#sources) and their commits.

## Short answer

- Farley's ATDD skill is a Claude Code plugin, `msec`, published by
  Continuous Delivery Ltd in the public repo `cd-training-courses/claude-skills`
  [F3]. The repo has no license, so jidoka may not carry or edit a copy. The
  files are only a thin client for a content server behind a sign-in
  [F3][F4].
- Any email gets lesson summaries free. The full lessons come with the £599
  ATDD course, which the video sells at 30% off [F1][F2][F3].
- It teaches the four layers and spec-first in detail. It never asks the
  agent to watch a new spec fail, never keeps specs out of the agent's
  reach, and never mentions mutation testing [F4].
- C#: Stryker.NET is maintained, and `--since` mutates only what changed
  since a commit [S2].
- C++: Mull and dextool need Clang and LLVM and document no Windows or
  MSBuild support [M1][M2][D1]. Both mutate only the lines a git diff
  touched [M3][D2]. universalmutator rewrites text and takes any build
  command [U1].
- Python: mutmut runs on Windows only under WSL and has no diff filter [P1].
  cosmic-ray takes any test command and has a git filter [R1].
- With 20-minute suites, diff-only runs are the only practical mode.

## 1. Farley's ATDD skill

**Where it is.** The captions give no link, but the video description says
"Discount on ATDD Course + Claude ATDD Skill" with `bit.ly/4rSAONz`, and
"Save 30% NOW and get my ATDD Skill FREE" [F1]. The link redirects to the
course page with `?coupon=atdd30` (`curl`, 2026-10-21). That page says "NOW
WITH FREE Claude ATDD Skill", lists a lesson "Acceptance Testing with AI and
the ATDD Skill", and prices the course at £599 [F2]. The plugin is public at
`github.com/cd-training-courses/claude-skills`, in an organization named
CD.Training, with "Continuous Delivery Ltd" as marketplace owner
[F3 marketplace.json:4]. Web searches found no post about it on Farley's
blog or Substack, and `gh api users/davefarley77` returns 404.

**License and price.** No LICENSE file, and GitHub reports none [F3], so
default copyright applies. A free sign-in gets "lesson summaries"; an email
registered to the course gets "full lesson bodies as Dave wrote them"
[F3 README:112-115]. The sibling Farley Score plugin, a test-quality scorer,
is MIT and could be carried [F5].

**Format and harness.** Four Markdown files under `commands/` with only a
`description` front matter, not `SKILL.md`, plus an HTTP MCP server declared
in `plugin.json` [F3]. It targets Claude Code alone: `/plugin` install,
`AskUserQuestion` menus, `claude mcp` repair steps. One line allows a
numbered list "if these files are run in another agent"
[F4 atdd-build:137]. The commands are `atdd-learn`, `atdd-build`,
`atdd-review` and `signin`.

**What `atdd-build` walks through** [F4 atdd-build:177-306]:

- Treat ATDD as feedback on the spec. Locate a failure's layer before
  fixing it.
- Find the boundary of the system under test, and extend any half-built DSL
  or driver code rather than start a second one.
- Spec first, "non-negotiable": Given/When/Then, 3 to 5 lines, one outcome,
  domain language, and the check "could this spec be fulfilled by a
  completely different implementation?"
- DSL: named parameters with defaults, aliasing for isolation, one class per
  domain area. It maps Farley's Java pattern to Python, TypeScript, C# and
  Go. C++ is absent.
- Protocol drivers behind an interface, atomic steps, assertions in the
  driver, poll with a timeout. Stubs are translators.
- One spec, one DSL method, one driver method at a time: "Each phase is its
  own commit, landing green before the next begins."
- No skipped failing tests; use strict expected-failure markers.
- Commit to `main` by default; write a dated findings note at session close.

`atdd-review` checks existing tests on seven counts: spec quality, four
layers, isolation, DSL, drivers, intermittency, and honest status
[F4 atdd-review:175-222].

A grep of all four files finds no step that runs a new spec to see it
fail, no rule protecting specs from the agent or requiring a human to
approve spec changes, and no mention of mutation testing. The substance
lives on the server, and the skill tells the agent "Do not fall back to your
own general knowledge of ATDD" when the server is down [F4 atdd-build:119].

## 2. Mutation testing tools

| Tool | Latest release | Build and platform | Tests | Mutate only the diff | Reuse earlier runs |
|---|---|---|---|---|---|
| Stryker.NET [S1][S2] | 5.0.0, 2026-09-11 | .NET Core and Framework; .NET 10 runtime; Framework needs the `.sln` | VSTest; Microsoft Testing Platform in preview | `--since:<commit>` | `--with-baseline`, stored on disk, Dashboard, Azure or S3 |
| Mull [M1][M2][M3] | 0.34.2, 2026-10-17 | Clang/LLVM 16 to 23, Linux and macOS; WSL unofficial; no Windows packages | Any test binary that exits non-zero on failure | `gitDiffRef` | Not documented |
| dextool mutate [D1][D2] | v5.3, 2025-09-09; last commit 2026-04-20 | libclang 14+, built with the LDC D compiler; reads `compile_commands.json` | Any command | `--diff-from-stdin` | SQLite database; resumes; retests survivors when tests are added |
| mutate_cpp [N1] | No releases; last commit 2024-06-30 | Any build command | Any command | A line range per file | Not documented |
| universalmutator [U1] | 1.14.1, 2026-05-20 | Text rewriting, any language | Any command | `--lines <file>` | Not documented |
| mutmut [P1] | 3.8.0, 2026-09-12 | Needs `fork`; WSL on Windows | pytest | No; name globs, `mutate_only_covered_lines` | Retests only functions whose source changed |
| cosmic-ray [R1] | 8.7.0, 2026-08-09 | README claims Windows and POSIX | Any command | `cr-filter-git` against a branch | Resumable SQLite session; HTTP workers |

**Caveats.** Stryker treats every mutant covered by a changed test file as
changed [S2:488], and `--since` excludes `--with-baseline` [S2:536]. Mull
hooks in through the compiler flag `-fpass-plugin` [M4], dextool through a
compilation database that CMake writes [D3]. Neither documents MSBuild, and
Mull's "Windows support" issue has been open since 2023 [M2].

**Run time.** I found no published large-codebase timings. cosmic-ray: a
10-second suite with 1,000 mutants takes about 2.7 hours [R2]; by the same
sum a 20-minute suite takes about 14 days on one worker. dextool: a full
run "may be weeks (one worker)"; run master in 3 to 9 hour batches and pull
requests under `--max-runtime "10 minutes"` [D2:27-30,78,100]. What cuts
the cost: Stryker.NET and dextool compile all mutants into one build
[S3][D1]; Mull builds one binary but runs the test program once per mutant
[M5:23-28]; Stryker runs only the tests covering each mutant by default
[S2:435-447]; mutmut "knows which tests to execute" [P1:21].

## 3. Mutation testing with agents

- Farley: "If a mutant survives, then your specification has a hole in it"
  [T1:229-231].
- Robert C. Martin's `swarm-forge` gives mutation work to a "hardener"
  agent. It runs mutation "always differential against the source
  manifest", and mutates the Gherkin acceptance specs with `gherkin-mutator`
  before handing off to QA [B1:10-11,35-39].
- Meta's ACH has an LLM write mutants for one concern, then tests that kill
  them: 9,095 mutants, 571 tests, 73% accepted by engineers, plus an LLM
  agent that flags equivalent mutants [G2].
- Google mutates only changed code, at code review, across two billion
  lines [G1].
- Deleting tests: dextool reports tests that kill no mutants, or only
  mutants others kill too [D1:33-35]. Stryker's `--disable-bail` helps "find
  useless unit tests" [S2:463]. Neither says to delete them. A test that
  kills no mutant may still be the only executable statement of a
  requirement, so I would treat the list as a review queue.

## Could not confirm

- What the paid lessons say, including on red first, spec protection or
  mutation testing. I did not sign in.
- Whether the course hands out anything beyond the public repo, or grants a
  license.
- Where Fowler recommends pairing acceptance tests with mutation testing, as
  Farley says he does [T1:229-230].
- Large-codebase timings for Stryker.NET or Mull.
- Whether Mull or dextool work with clang-cl, or universalmutator on Windows.

## Sources

- [F1] https://www.youtube.com/watch?v=EkH_uoybj8k, description, read 2026-10-21.
- [F2] https://courses.cd.training/courses/atdd-from-stories-to-executable-specifications
- [F3] https://github.com/cd-training-courses/claude-skills at `83e4dac`: `.claude-plugin/*.json`, `README.md`.
- [F4] Same commit, `commands/atdd-build.md`, `commands/atdd-review.md`.
- [F5] https://github.com/cd-training-courses/farley_score_plugin, `LICENSE`.
- [T1] `docs/transcripts/the-industry-is-catching-up.md` on `main` at `0868551`.
- [S1] https://github.com/stryker-mutator/stryker-net/releases
- [S2] stryker-net `docs/configuration.md` at `02e1307`; [S3] `docs/technical-reference/mutant-schemata.md`.
- [M1] https://github.com/mull-project/mull/releases/tag/0.34.2; `docs/Features.rst:8-10,31-32` at `5ac9d61`.
- [M2] `docs/HowMullWorks.rst:87-92`; https://github.com/mull-project/mull/issues/1039
- [M3] `docs/IncrementalMutationTesting.rst`; [M4] `docs/tutorials/CMakeIntegration.rst:38-40`; [M5] `docs/HowMullWorks.rst`.
- [D1] https://github.com/joakim-brannstrom/dextool at `32bdcad`: `README.md:27-53`, `plugin/mutate/README.md`.
- [D2] `plugin/mutate/README_ci.md`; [D3] `plugin/mutate/README_tutorial_fmt.md:36-61`.
- [N1] https://github.com/nlohmann/mutate_cpp, `README.md`.
- [U1] https://pypi.org/project/universalmutator/; `universalmutator/genmutants.py:146-147`.
- [P1] https://pypi.org/project/mutmut/; `README.rst:20-36,50,151-170,514` at `7d5fff3`.
- [R1] https://pypi.org/project/cosmic-ray/; `README.rst:28`, `docs/source/concepts.rst:36-86`, `docs/source/how-tos/filters.rst:92-103` at `f6550ad`.
- [R2] `docs/source/tutorials/intro/index.rst:309-312`, same commit.
- [B1] https://github.com/unclebob/swarm-forge, branch `six-pack` at `066a62f`, `swarmforge/roles/hardender.prompt`.
- [G1] Petrović et al., "Practical Mutation Testing at Scale", https://arxiv.org/abs/2102.11378
- [G2] Foster et al., "Mutation-Guided LLM-based Test Generation at Meta", https://arxiv.org/abs/2501.12862
