# The address carries the active project

The browser held the active project, so every tab shared one choice. A
link to a board or a bead named no project and read the one that the
browser held last. A switch in one tab therefore changed what a link in
another tab meant, and the next reload of that tab opened the wrong
project. A bead opened from the needs-you view made its project active,
so the browser held that one as well, and the person had not asked for it.

The address of every page that shows one project now carries that
project: the board, the detail page and the doctor page. The browser holds
no project. Each tab keeps the last project that an address named, in
memory alone, for the pages that belong to no project, such as the
needs-you view and the list of projects. The address beats that memory.
This supersedes [ADR 0007](0007-the-browser-holds-the-active-project.md).

## Considered options

The storage of one tab would have outlived a reload, and a switch in
another tab could not reach it. It is still storage that the browser
holds, and a link copied from that tab would still name no project.

## Consequences

A pick in the project picker is a navigation. The board and the detail
page go to the board of the new project, the doctor page goes to the
doctor page of the new project, and the pages that belong to no project
stay where they are. Back undoes a switch.

An address that names no project, such as an old bookmark, takes the
project that the tab remembers and replaces itself with an address that
names it, so a link copied from the address bar always names its project.
A tab that remembers none asks the person to pick one. An address that
names a project the registry no longer holds says so, and it does not
fall back to the project that the tab remembers.

A fresh tab at the root of the app starts with no project, and the list
of projects there links each one to its board.

Browsers that ran an earlier build still hold the old storage key. Nothing
reads it, and the app does not remove it.
