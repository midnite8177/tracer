# tracer-seed

The sources and the build of the tracer seed, the one file that installs
tracer into a repo.

## Language

**Seed**:
The single Markdown document that `/tracer:adopt` reads and follows to
install or re-align tracer in a repo. `build.py` generates it; nobody
edits it by hand.
_Avoid_: Spec, install script, tracer.md (as a concept)

**Revision**:
The seed's version number, raised once per released change and named by
the first changelog entry.
_Avoid_: Version, release

**Fragment**:
One source file of the seed's prose under `src/fragments/`. `seed.json`
gives the order fragments join in.
_Avoid_: Chunk, section, part

**Maintainer notes**:
The text at the top of a fragment, above the seed marker, that says why
the fragment has its shape. The build drops it.
_Avoid_: Why header, comments

**Installed file**:
A file the seed carries verbatim and adopt writes into a repo: a skill
body, an agent, a script, a `docs/agents/` doc. It lives under
`src/installed/` and reaches the seed through an include.
_Avoid_: Embedded file, payload

**Block**:
A numbered part of the seed, grouped by who reads it at runtime: Block 1
is AGENTS.md, Block 2 is `docs/agents/`, Block 3 the patches, Block 4 the
native and carried skills, Block 5 the status line.

**Upstream pin**:
The tag of `mattpocock/skills` that adopt fetches. One value in
`seed.json`.
_Avoid_: Upstream version

**Patch**:
A numbered, described edit to one upstream skill, anchored to text in that
skill, such as P1 for `implement`.
_Avoid_: Fork, override

**Carried skill**:
A small third-party skill copied verbatim into the seed with its source,
commit and deltas recorded, rather than fetched from a second pin.
_Avoid_: Vendored skill, bundled skill
