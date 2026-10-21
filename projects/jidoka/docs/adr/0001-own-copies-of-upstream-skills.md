# 0001 — Own copies of upstream skills

Tracer fetched Matt Pocock's skills at a pinned tag when it adopted a repo,
then patched them by matching anchor text. One move of that pin took a
306-line change, a file rename and a new rule for matching anchors. jidoka
installs as a plugin, and a plugin carries finished files, so jidoka owns
a copy of every skill it carries and edits each copy as far as jidoka
needs. Each copied SKILL.md names its upstream and the upstream commit it
was copied from, in `metadata.upstream` and `metadata.upstream-base`. A
maintainer script runs only when Jeff decides to take upstream changes. It
compares that base, upstream today and jidoka's copy, replaces an unedited
skill whole, and shows upstream's change beside jidoka's for an edited one
so he can port it by hand. The edited skills lose automatic updates, and
in exchange no patch breaks when upstream rewords a line. jidoka's review
skills come from tracer, and jidoka does not depend on the separate smells
plugin.
