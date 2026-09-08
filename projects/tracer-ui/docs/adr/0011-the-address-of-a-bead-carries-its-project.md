# The address of a bead carries its project

A bead id means nothing outside the project that holds it, and the browser
holds the active project of a session. A tab that the browser opens beside
another one starts with no session of its own, so a row of the needs-you
view could not hand a bead of a second project to a new tab: the tab would
read the project that the browser held. The address of the detail page now
carries the project of the bead in its query, and the page makes that
project the active one before it reads the bead.

## Consequences

A row of the needs-you view is a link, so a person opens a bead there the
way a person opens one on the board.

There are two sources of the active project, and the address beats the
browser. The browser still holds the choice, so a plain address of a bead,
which the board writes, still reads the project of the browser. See
[ADR 0007](0007-the-browser-holds-the-active-project.md).

A tab that opens a bead of another project makes that project active, thus
the browser holds it and the next fresh tab starts there. This is the same
switch that a press in this tab makes, and the top bar names it either way.
