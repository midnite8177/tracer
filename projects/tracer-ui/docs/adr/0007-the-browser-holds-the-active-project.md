# The browser holds the active project

The active project lived in the circuit alone, so a reload of the page and a
second tab both lost it and sent the person back to the picker. The choice
must outlive the circuit, and there were two places to hold it: the browser,
beside the theme, or the registry file, beside the projects and the saved
filters.

The browser holds it. The glossary already calls the active project the one
project that the current browser session looks at, and this keeps that
sentence true: two browsers, and two machines in LAN mode, each keep their own
choice. The registry file holds what the person owns for every session, and
one shared choice there would make a switch in one tab change the next tab of
another person on the network.

`ActiveProjectSelection` holds the storage key and the rule that guards a
stored path. The project picker asks the browser for the path at its first
render, and it gives back the path of each switch, as the theme toggle does
with the theme.

## Consequences

The storage of a browser is out of reach until the page is interactive, thus
the top bar reads "Select a project" for the first render of a reload and then
names the project. The theme escapes this with a script that runs before the
first paint. The project cannot: the pages read the choice on the server, and
the server learns it only when the circuit is live.

A stored path that leaves the registry restores nothing, and the person picks
again. A browser that refuses its storage costs the person one pick for each
reload, and nothing else fails.
