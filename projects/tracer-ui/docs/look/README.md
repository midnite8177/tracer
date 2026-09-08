# The look of tracer-ui

This directory holds the checklist that closes the look. The shots
themselves stay out of the repository. A shot of this app carries whatever
backlog it was pointed at, which means the paths, the addresses and the
bead titles of the person who took it, so each reader takes their own
against a backlog of their own.

Shoot from a window 1280 pixels wide. Every shot but the four detail shots
carries the first screen of the page. Those four carry the whole page,
because the prose column runs under the description and its boxes are the
part that a reader must judge.

The detail page takes two shots per theme, because no one bead draws every
box. A leaf bead draws the close reason, the dependencies and the comments,
and an epic draws the held beads.

## The checklist

### No color is stated outside the token file

`wwwroot/tokens.css` states every color. No other stylesheet, no `.razor`
file and no C# file states a color, an `rgb` value or a color name. The
keyword `transparent` is not a color: it is the absence of a fill, and a
rule that wants no fill states it wherever it stands.

Two rules guard this:

- The light block and the dark block define the same token names. A name
  that only one block carries is a defect.
- Every `--tracer-` name that a stylesheet reads is a name that the token
  file defines, and every name that the token file defines has a reader.

Bootstrap ships a color of its own for each control that the app does not
name. `wwwroot/bootstrap-overrides.css` gives each control the tokens
instead, and a control that the app uses and that file does not map is
therefore also a defect, even though it states no color itself.

`wwwroot/favicon.svg` carries its own colors. It is an image, not a
stylesheet, and a favicon must read the same in both themes.

### The contrast of text on the page passes at the normal size

Every text token reaches at least 4.5:1 against the five grounds that text
rests on — the canvas, the subtle canvas, the inset canvas, the overlay
canvas and the hover ground — in both themes. The lowest is the danger text
on a hovered row in the dark theme, at 4.54:1. The lowest in the light theme
is the muted text on a hovered row, at 5.24:1. Text on white reads at
15.80:1, and text on black at 16.02:1.

The hover ground set six of these values. A hovered row is darker than the
page in the light theme and lighter than the page in the dark one. Six pairs
of a text token and a hovered row read between 4.08:1 and 4.50:1 with
GitHub's own shades, and every one of them passes on a resting row. Each
text token therefore takes the shade that passes on every ground, and each
new value is GitHub's own: the four colored names of the light theme take
the next darker shade of the same scale, and the two muted names take
GitHub's later grey.

| Token | Light | Dark |
| --- | --- | --- |
| `--tracer-fg-muted` | `#656d76` → `#59636e` | `#7d8590` → `#9198a1` |
| `--tracer-accent-fg` | `#0969da` → `#0550ae` | `#58a6ff` |
| `--tracer-success-fg` | `#1a7f37` → `#116329` | `#3fb950` |
| `--tracer-attention-fg` | `#9a6700` → `#7d4e00` | `#d29922` |
| `--tracer-danger-fg` | `#d1242f` → `#a40e26` | `#f85149` |

The hover grounds themselves keep GitHub's values, because the active row of
the registry rests on the subtle canvas and must still answer the pointer. A
light hover ground that passed on its own would have to reach that canvas,
and the row would then answer nothing.

A name that ends in `-fg` carries text, and a name that ends in `-emphasis`
carries a fill under white text. The two need not hold one value: a text
shade answers to the ground behind it, and a fill answers to the white on
top of it. In the light theme they differ, so a link takes a darker blue
than the primary button and the focus ring, which share one value.

### The contrast of text on the top bar passes at the normal size

The bar does not rest on the grounds of the page. It has three grounds of its
own: its canvas, its hover ground and its selected ground. The canvas is a
color. The other two are white at a low opacity over that canvas, so the
browser composites them before it paints the text.

| Ground | Light | Dark |
| --- | --- | --- |
| `--tracer-topbar-canvas` | `#24292f` | `#161b22` |
| `--tracer-topbar-hover` | 10% white → `#3a3e44` | 8% white → `#292d34` |
| `--tracer-topbar-selected` | 25% white → `#5b5e63` | 15% white → `#393d43` |

The bar has two text tokens. `--tracer-topbar-fg` is the full strength text,
and `--tracer-topbar-fg-muted` is the quiet text. The muted token meets the
canvas alone, because every control that takes the hover ground or the
selected ground carries the full strength text color under the pointer. Three
controls take those grounds. The nav link and the theme toggle rest in the
muted color and change to the full strength one in the same rule that paints
the ground. The project picker carries the full strength color at rest, so it
never wears the muted token at all.

| Text on ground | Light | Dark |
| --- | --- | --- |
| full strength on the canvas | 14.65:1 | 14.64:1 |
| full strength on the hover ground | 10.76:1 | 11.70:1 |
| full strength on the selected ground | 6.51:1 | 9.24:1 |
| muted on the canvas | 10.09:1 | 4.64:1 |

The lowest of the eight pairs above is the muted text on the canvas of the
dark theme, at 4.64:1. The lowest pair that a control reaches under the
pointer is the full strength text on the selected ground of the light theme,
at 6.51:1. Every pair passes.

That margin comes from the rule and not from the shades. The muted token fails
on both of the composited grounds: it reads 4.48:1 on the selected ground of
the light theme, and 3.71:1 on the hover ground of the dark one. A control
that keeps the muted color under the pointer is thus a defect, even though
every value in the table above passes.

### The keyboard focus ring is visible on every control that takes focus

The ring has two token names, because the light theme puts a white page
beside a near-black bar and one color cannot stay legible on both:

- `--tracer-focus-ring` on the page: 5.19:1 in the light theme, 5.66:1 in
  the dark one.
- `--tracer-topbar-focus-ring` on the bar: 6.19:1 in the light theme,
  5.17:1 in the dark one.

Both hold at least 3:1 on every ground that they meet, which is what a focus
indicator needs. One width token gives both rings their thickness, so the
page and the bar cannot drift apart.

A disabled control paints no ring, which is correct.

### The copy button says its outcome in more than the icon

The button that puts machine text on the clipboard says its outcome three
ways, because no one of them reaches every person:

- The icon and the title change together, from the one value that the
  session holds, so the picture and the words never disagree.
- A press that reached no clipboard also puts the reason in words beside
  the button. A title needs a pointer resting on it, a phone has none, and
  the phone is where the refusal happens.
- A live region says the outcome, because a screen reader reads neither the
  icon nor a label that changes under a person already standing on the
  button. The words beside the button stay out of that region, so the
  reason is read once.

### Every page renders in both themes

Eighteen shots close this item: eight pages in two themes, and the detail
page twice.

- Projects
- Add a project
- Board
- Detail, a leaf bead
- Detail, an epic
- Needs you
- Doctor
- Not found
- Something failed

A page that loads in the dark theme shows no flash of the light one. The
script in the document head sets the theme before the body renders.

Read a shot against the shades that the token file holds on the day it is
taken.
