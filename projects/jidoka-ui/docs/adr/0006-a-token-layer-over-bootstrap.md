# A token layer over Bootstrap carries the look

The app started from the Blazor template and looks like it, and the two
other ways to change that were to drop Bootstrap for hand-written CSS, or
to adopt a Blazor component library. The app keeps Bootstrap 5.3 and adds
a design token layer that overrides Bootstrap's own variables, because
that reaches every page without a change to any markup, and because
Bootstrap 5.3 already carries the theme attribute that the light and the
dark theme need. A component library rewrites every page for a look, and
puts a large dependency between the app and `bd`.

## Consequences

No page states a color of its own. A color outside the token file is a
defect, and a review can cite this decision.

One exception holds: an asset that the browser loads without a
stylesheet. The favicon is such an asset, because a browser gives it no
CSS and thus no token can reach it. Such a file states its colors, and
it names in a comment which token each one copies, so that a change to
the accent finds it.
