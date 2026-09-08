# The address of the board carries the filter

The board held its filter in the state of the component, so the address of
the board was `board` whatever a person was looking at. A person could not
send a narrowed board to somebody, open one in a second tab, or press Back
to undo a change of the filter. The whole filter now lives in the query of
the address. The board reads the address, and the filter bar and every
filter press write it.

## Consequences

Every change of the filter is a navigation, so the browser keeps a history
of the board. The search text is the one exception: it binds on each key,
and a history entry for each letter would bury the entry that a person
wants, so a change of the text alone replaces the address instead of adding
to the history.

A filter press is therefore a link and not a button, which gives it the
middle-click and the copy-link that a person expects of one. It also gives
it the address of the whole filter with the one part that the press sets,
so a press adds to the filter and never replaces it.

The bead selection and the collapsed rows stay in the component, because
they are what a person is doing and not what a person is looking at.
