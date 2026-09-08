# A doc comment marks the public contract

The repo carries 694 doc comments, and 232 of them sit on a member
declared private. No one outside the file can read those. The editor does
not offer one to a caller, and the only person who ever sees it is already
reading the line below it. The prose in them is worth keeping. A sample of
fourteen at random held not one restatement of a name: they say why a
fixture is shaped as it is, why a filter change replaces the address
instead of adding to the history, why a picker stays open on a write that
`bd` refused. It is the `///` that is wrong, because the three slashes
claim an audience the member does not have, and a claim like that is what
rots. A reader trusts a doc block more than a comment, and trusts it
longer.

So `///` marks what a caller in another file reads, and nothing else. That
is every public and internal member, every `[Parameter]` of a component,
and every protected member of a base class that a component elsewhere
inherits, such as the write helpers of `CapabilityAware`. A private
member, and an override of a member the base class already documented,
carries the same sentences under `//`.

Two shapes need the rule spelled out, because their modifier does not
answer the question. A member that is public only so that something in its
own file can reach it, such as a nested type no other file names or an
enum that `[InlineData]` forces open, has no caller elsewhere and follows
the private rule. An enum member carries no modifier at all, so it takes
the marker of its enum: the members of a public enum keep `///`, and the
members of a private one drop to `//` with it.

## Consequences

The rule is about the marker, not the words. Every sentence in those 232
blocks survives the change, in the same place, saying the same thing. A
pass that applies this ADR is a rewrite of the punctuation, and it may
delete no prose. Anything worth cutting is a separate reading with its own
judgment.

A `[Parameter]` is documentation whatever the catalog of smells says about
a header on every member. It is the way another component passes a value
into this one, and the editor puts the sentence in front of the person
writing that call. A component's parameters are its signature.

The line from the root conventions still stands: a doc comment says what a
type is, or why it has its shape, and never what the work was. The `//`
comments this ADR creates take the same rule with them. Demoting the
marker does not license a note about a bug, a date, or a bead.

An analyzer could hold most of this rule where a reviewer now holds it.
The clause about a member that is public for its own file alone needs a
reader who knows who calls it, so a tool would have to leave that one
behind. Nothing enforces any of it today, and the repo has no lint step to
hang it on.
