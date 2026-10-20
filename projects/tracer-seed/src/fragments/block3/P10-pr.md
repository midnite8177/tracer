`pr` is usable by hand as a review guide for any range (bead id, range,
commit, or current work). It pins the range the way `code-review` does,
prints what it covers, uses text forms where Mermaid will not render,
offers to write to a named path, and never opens a PR. It stays
model-invoked for real PRs.

<!-- seed -->
**P10 · `pr` — usable by hand as a review guide, for any range.**
The body (the template and the Sections guidance) stays as upstream
wrote it; it is a format reference and is model-invoked, so it also
fires on its own when a PR body is being written. Add the frontmatter
line `argument-hint: "[bead-id | <fixed-point>..HEAD | commit | nothing]"`
and prepend to the body:

> The output is a **review guide**: the same three sections whether it
> becomes a pull request body, a Perforce review description, or a file
> handed to a reviewer. Nothing here opens a PR or a changelist.
> First pin the range, in the order `code-review` uses: a range or
> commit the user passed; a bead id, whose `implement started at <sha>`
> comment gives the fixed point (`bd show <id>`); otherwise the working
> tree plus commits since the merge-base with the default branch, and
> say which. Print `git log <range> --oneline` (or the shelved or
> pending changelist's file list under Perforce) in one line so the
> reader knows what is covered, then write the guide from the diff, not
> from memory of the session. Read `GLOSSARY.md` for the vocabulary.
> Evidence comes from things actually run or captured in this session;
> never describe a test run that did not happen. Mermaid does not render
> in a terminal: when the guide is going anywhere other than a Markdown
> renderer, use the text forms (pseudocode, trees, diffs) instead.
> Output the guide as Markdown in the reply, then offer once to write it
> to a path the user names; do not write a file unasked, and never into
> the repo unless they say so. Call the Skill tool with "unslop" on the
> prose before presenting it.

Bead ids and requirement ids follow the house rule: the guide names the
work by title, never by id.

