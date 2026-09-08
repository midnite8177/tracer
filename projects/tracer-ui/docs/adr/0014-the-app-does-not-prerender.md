# The app does not prerender

`App.razor` renders the whole router subtree as one interactive region, so
no page can choose a render mode of its own. Three pages carried a mode
anyway, and a measurement found all three inert. The question they were
reaching for was still open, so it is answered here for the app.

Prerendering is off. The needs-you page held its response 1.24 seconds over
two registered projects, and the detail page held it 2.0 seconds over one,
because each ran `bd` before its first render and the circuit then ran it
again. The board paid a different price: it guards on the active project,
which the browser holds and no prerender pass can know, so it drew "Select
a project first" and the circuit threw that away. See
[ADR 0007](0007-the-browser-holds-the-active-project.md).

## Consequences

Every page arrives as an empty document that the circuit fills. The pages
that read `bd` already say what they are doing while they read, so a person
sees the heading and that sentence at once instead of a blank tab.

A search engine reads none of this app, and nothing else does either. It
binds `localhost` and one person opens it, so the first paint is the only
thing prerendering could have bought, and it cost a doubled read to buy it.

The render mode lives in `AnInteractiveApp`, which `App.razor` names twice.
A page that states a mode of its own is a mistake, not a choice.

A test that reads a whole HTTP response needs the app in its own process,
so the tests carry `Microsoft.AspNetCore.Mvc.Testing` beside bUnit. The two
answer different questions and neither replaces the other: bUnit renders one
component and reads its markup, which is the right tool for almost every
test here and the one [ADR 0009](0009-bunit-renders-a-component-in-a-test.md)
chose. `WebApplicationFactory` is for what only the whole app can answer,
such as what a response holds before any circuit exists. Reach for it there
and nowhere else. It also needs the app to open no browser tab of its own,
which is why the tab sits behind `IStartupBrowser`.
