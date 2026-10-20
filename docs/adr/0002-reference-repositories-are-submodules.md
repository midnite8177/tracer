# 0002 — Reference repositories are submodules

Some outside repositories are kept on disk to read while designing tracer's
own work, and some of them carry no license. Each one is a git submodule
under `reference/<name>/`, pinned to a commit, instead of a vendored copy
or a subtree. A submodule records only a URL and a commit, so this
repository redistributes none of the upstream files, and moving the pin is
a reviewable commit. The cost is that a fresh clone needs
`git submodule update --init` before the files appear. `reference/` sits
outside `projects/` because it holds no project of this repository's own,
and agents may not edit it.
