# 0009 — The bead keeps the record, and a page explains it

Jeff takes in work through diagrams and examples far better than through
prose, and a bead comment is plain text. So every moment that needs him
gets two things. The bead gets the whole record in plain Markdown, with
text diagrams only, and it reads the same in `bd show`, in tracer-ui and
on a machine where tracer-ui is not running. Where a picture or an
example helps, jidoka also writes a page, one self-contained HTML file in
`~/.jidoka/pages/<repo>/` and never in the repo. tracer-ui serves the page
beside its bead and draws the page's controls itself, such as the answer
panel at a question and Merge and Send back at the acceptance gate,
because tracer-ui writes through `bd` and a file on disk cannot write at
all. Markdown alone could not carry the diagrams, the before-and-after
examples or a diff Jeff can browse file by file, and T3's `html_render`
exists only at home. The cost is that the pages are comfortable only
where tracer-ui runs, and that a page can fall behind its bead. When the
two disagree, the bead wins.
