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

The address of every page that shows one project now carries it, and the
browser holds no project at all. A tab that opens a bead of another project
makes that project active in that tab alone, so it changes no other tab.
See [ADR 0016](0016-the-address-carries-the-active-project.md).
