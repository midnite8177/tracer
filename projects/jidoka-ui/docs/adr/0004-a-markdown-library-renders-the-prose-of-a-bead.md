# 0004 — A markdown library renders the prose of a bead, and raw HTML never passes

The description, the acceptance criteria and the notes of a bead are
markdown, and a detail page that shows them as one run of text hides the
Demo and the Seams sections that the work depends on. Markdig renders
them, because a hand-written parser of headings, lists, code and links is
a source of defects that returns nothing the app needs. The renderer runs
with raw HTML disabled: an agent and a person both write these fields, the
page puts the answer into the document without a further escape, and a
description is therefore never a way to run a script in the browser.
