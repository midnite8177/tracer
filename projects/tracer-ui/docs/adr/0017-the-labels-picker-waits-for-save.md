# The labels picker waits for Save

Every other pick on the detail page writes at once, and the labels picker
did too: one `bd label` run for each tick. A person who changes three labels
means one change, but got three writes and three re-reads. The labels picker
now keeps each press as an unsaved tick, and Save sends them all in one
`bd update` with `--add-label` and `--remove-label`. It sends only what
changed, never the whole set, so that a label an agent adds while the picker
is open survives the Save.

This supersedes the paragraph of [ADR 0012](0012-press-to-edit-on-the-detail-page.md)
that keeps a labels picker open after each write.
