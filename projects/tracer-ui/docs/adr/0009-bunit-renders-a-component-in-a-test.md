# 0009 — bUnit renders a component in a test

Some facts live in the markup alone: a message reaches the eye, or a
stylesheet hides it from every reader but a screen reader. No test of this
app could observe such a fact, because every test called a class of
`TracerUi.Core` and no test rendered a component. bUnit renders one
component into a DOM that a test queries, so the test asks the markup what
a person sees.

## Consequences

The test project takes a dependency that the app itself does not need, and
a test can now name a CSS class. We accept the second cost: the class name
is the public shape of the markup, as a method name is the public shape of
a class, and a test that asks for the words alone cannot tell a visible
message from a hidden one.
