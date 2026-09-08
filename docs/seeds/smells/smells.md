# Smells

A single catalogue of code smells and comment smells, in the style of Fowler's *Refactoring*. Part 1 is Fowler's catalogue (2nd ed., 2018) with fixes and language notes. Part 2 is a comment-smell catalogue, blending Robert Martin (*Clean Code*, ch. 4), Fowler, and Hunt & Thomas (*The Pragmatic Programmer*). Applies to C++, C#, and Python.

A smell is a hint, not a verdict. Each entry names what it looks like, why it hurts, and the refactoring that fixes it.

---

# Part 1 — Code Smells (Fowler)

Grouped by the kind of damage they do.

## Bloaters — things that have grown too large

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Long Function** | A function you have to scroll; many locals; nested blocks | Hard to name, test, and reason about | Extract Function; Replace Temp with Query; Decompose Conditional; Replace Function with Command |
| **Large Class** | Many fields, many methods, many reasons to change | Responsibilities tangled; duplication hides inside | Extract Class; Extract Superclass; Replace Type Code with Subclasses |
| **Long Parameter List** | 4+ parameters; several always passed together; a flag parameter | Hides an object that should exist; callers get it wrong | Introduce Parameter Object; Preserve Whole Object; Replace Parameter with Query; Remove Flag Argument |
| **Data Clumps** | The same 2–3 fields travelling together (x, y, z; start, end; host, port) | Missing abstraction; each copy drifts | Extract Class; Introduce Parameter Object |
| **Primitive Obsession** | `string` for an ID, `int` for money, `float` for an angle, tuples for records | No type safety; validation scattered; units confused | Replace Primitive with Object; Replace Type Code with Subclasses; Replace Conditional with Polymorphism |

## Change Preventers — things that make change expensive

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Divergent Change** | One module edited for many unrelated reasons | Unrelated concerns share a home; every change risks the others | Split Phase; Extract Class; Move Function |
| **Shotgun Surgery** | One logical change touches many modules | Easy to miss one; the concept has no home | Move Function; Move Field; Combine Functions into Class; Inline Class |
| **Repeated Switches** | The same `switch` / `if-else` chain on the same type in several places | Adding a case means finding every switch | Replace Conditional with Polymorphism |
| **Global Data** | Static mutable state; singletons with setters; module-level mutable variables | Anyone can change it; nothing is local | Encapsulate Variable; narrow the scope |
| **Mutable Data** | Values changed from many places; shared references mutated | Bugs appear far from their cause | Encapsulate Variable; Split Variable; Separate Query from Modifier; Change Reference to Value |

## Dispensables — things that don't earn their keep

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Duplicated Code** | Same logic in two places; near-copies with small edits | Fix one, forget the other | Extract Function; Slide Statements; Pull Up Method |
| **Lazy Element** | A class or function that does almost nothing | Indirection without benefit | Inline Function; Inline Class; Collapse Hierarchy |
| **Speculative Generality** | Hooks, abstract bases, and parameters for a future that never came | Complexity paid for, never used | Collapse Hierarchy; Inline Function; Remove Dead Code; Change Function Declaration |
| **Data Class** | Fields, getters, setters, no behavior | Behavior lives elsewhere and reaches in | Move Function (bring the behavior to the data); Encapsulate Record |
| **Dead Code** | Unreachable branches, unused functions, unused parameters | Reader has to work out it's dead | Remove Dead Code |
| **Comments** | Comment used as deodorant for unclear code | See Part 2 | See Part 2 |

## Couplers — things too tangled with each other

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Feature Envy** | A function that mostly uses another class's data | Logic lives away from its data | Move Function; Extract Function then Move |
| **Message Chains** | `a.GetB().GetC().GetD()` | Caller coupled to the whole path | Hide Delegate; Extract Function; Move Function |
| **Middle Man** | A class that only delegates | Indirection without value | Remove Middle Man; Inline Function; Replace Superclass with Delegate |
| **Insider Trading** | Modules passing private data back and forth; friends and internals abused | Encapsulation broken; hidden coupling | Move Function; Move Field; Hide Delegate; Replace Subclass with Delegate |
| **Temporary Field** | A field only set in some cases or phases | Reader must know when it's valid | Extract Class; Move Function; Introduce Special Case |

## Object-Orientation Abusers — inheritance and interfaces misused

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Refused Bequest** | A subclass that ignores or overrides most of its parent | Inheritance where there is no is-a | Push Down Method; Push Down Field; Replace Subclass with Delegate; Replace Superclass with Delegate |
| **Alternative Classes with Different Interfaces** | Two classes doing the same job with different APIs | Callers can't swap them | Change Function Declaration; Move Function; Extract Superclass |
| **Mysterious Name** | Names that don't say what a thing does or holds | Reader must read the body to learn the name | Change Function Declaration; Rename Variable; Rename Field |
| **Loops** | Index loops where a pipeline would read better | Intent hidden in bookkeeping | Replace Loop with Pipeline (LINQ, ranges/algorithms, comprehensions) |

## Language notes — code smells

| | C++ | C# | Python |
|---|---|---|---|
| Primitive Obsession | Raw `int`/`float` for handles, IDs, units; `std::pair`/tuples as records | `string` IDs, `int` enums, `Tuple<>` | Bare tuples/dicts as records; strings as enums |
| Global Data | Non-const globals, static locals, singletons | `static` mutable fields, service-locator singletons | Module-level mutable state, `global` |
| Repeated Switches | `switch` on enum/type tag; `dynamic_cast` chains | `switch` on enum; `is` pattern chains | `if isinstance` chains; dict-of-type dispatch repeated |
| Loops | Index loops instead of `<algorithm>`/ranges | `for` instead of LINQ | `for`+`append` instead of comprehension/generator |
| Insider Trading | `friend` abuse; reaching into `detail::` | `InternalsVisibleTo` abuse; reflection into privates | Reaching into `_private` members of another module |
| Refused Bequest | Overriding to throw or no-op | `NotSupportedException` overrides | Overriding to `raise NotImplementedError` in a concrete class |
| Data Class | Struct with getters/setters and no methods | Class of auto-properties with logic elsewhere | Class of attributes; consider `@dataclass` only if behavior belongs elsewhere by design |

---

# Part 2 — Comment Smells

## Principle

A comment carries what the code cannot. If the code could carry it, change the code. Comments are for humans. The code is the source of truth.

## The allowed set (good comments)

| Category | What it carries | Rule |
|---|---|---|
| **Intent** | Why this approach; what was rejected and why | Only when a name or extracted function could not say it |
| **Constraint** | An external fact the code obeys: protocol quirk, hardware limit, vendor bug, legal requirement | Name the source |
| **Warning** | A cost the *caller* pays: not thread-safe, allocates per call, O(n²), slow | Stops misuse |
| **Amplifier** | A line that looks removable but is load-bearing | Must name the failure that happens without it. "This matters" alone is a Mumble |
| **Invariant** | A condition the language cannot express | If an assert can express it, use the assert |
| **API Doc** | Doc comment on a public or internal member | Must say something the signature does not: preconditions, null/exception behavior, ownership, cost |
| **Legal Header** | Copyright/license | Short; point to the license file |

### The Deodorant test (Intent vs. Deodorant)

1. If you could name a function after the comment, it is Deodorant. Extract the function.
2. If the comment answers "why not the obvious way?", it is Intent. Keep it.
3. If the comment describes a constraint from outside the codebase, it is Intent (Constraint) regardless of the first two.

## The smells

| Smell | Looks like | Why it hurts | Fix |
|---|---|---|---|
| **Subtitles** | `// increment counter` · `# loop over users` | Duplicates the code. Drifts. Trains readers to skip comments | Delete. If it felt needed: Rename, Extract Function |
| **Deodorant** | A paragraph explaining a hairy block | Masks unclear code instead of fixing it | Extract Function named for the paragraph; Introduce Explaining Variable |
| **Echo** | `/// <summary>Gets the user.</summary>` on `GetUser` · `"""Return the config."""` on `get_config` | Noise. Hides the members with real docs | Improve (precondition, null/exception behavior, cost) or delete |
| **Empty Theater** | Formal doc comment (XML, Doxygen) on a private member | Ceremony with no audience. Goes stale | Delete; rely on the name. **Python: not a smell** (docstrings are convention; only flag Echo) |
| **Liar** | Comment and code disagree | Worse than no comment. Actively wrong | Fix or delete. Treat as a defect, not style |
| **Ghost Reference** | Names a function, class, flag, or file that no longer exists | Signals nobody reads comments here | Delete or update |
| **Sticky Note** | `TODO`, `FIXME`, `HACK`, `XXX` | Work hidden in code instead of the tracker. Never swept | Create a tracked item; delete the comment. Zero tolerance |
| **Zombie Code** | Commented-out code | Nobody deletes it; it rots forever | Delete. VCS remembers |
| **Ship's Log** | Change history at the top of a file | VCS's job. Always incomplete | Delete |
| **Autograph** | `// added by JD` · `@author` | VCS's job. Invites ownership silos | Delete |
| **Fence Post** | `#region` · `#pragma region` · `// ---- Helpers ----` · `# ===== Utils =====` | Fences inside a room mean the room is too big or mixes responsibilities | Extract Class, Move Function. Exception: generated code |
| **Breadcrumb** | `} // end while` · `} // namespace foo` · `# end if` | The block is too long to see its end | Shorten it. No exceptions; editors show the matching brace |
| **Gossip** | Describes what another file or class does | Won't be updated when that file changes | Move the comment to where the constraint lives. If it is a coupling, prefer a test or assert that fails when the coupling breaks |
| **Mumble** | `// handle the edge case` | Says something, means nothing. Reader cannot act on it | Name the edge case or delete |
| **Uniform** | A header on every function because a rule says so | Produces noise and lies | Remove the rule. Comment only when the allowed set applies |
| **Encyclopedia** | RFC excerpts, essays, history lessons | Buries the one line that matters | Cut to the constraint; link to the source |
| **Riddle** | A comment whose link to the code needs its own explanation | Reader does the work the comment was meant to save | Rewrite so the link is explicit, or move it next to its line |
| **Costume** | HTML/Markdown-heavy comment | Unreadable in the editor, where it is actually read | Plain text |
| **Prose Attribute** | `// obsolete` · `# deprecated` in words | The language has a real mechanism | `[Obsolete]`, `[[deprecated]]`, `warnings.warn` / `@deprecated` |
| **Price Tag** | `timeout = 30; // seconds` · `retries = 3  # max attempts` | The comment names what the literal should be named | Replace Magic Literal with a named constant |

## Language notes — comment smells

| | C++ | C# | Python |
|---|---|---|---|
| Doc comment syntax | Doxygen `/** */` or `///` | `///` XML docs | Docstrings |
| API Doc scope | Public + internal (exported / non-detail namespace) | `public` + `internal` | Public + `_private` both allowed |
| Empty Theater | Private members, `detail` namespaces | `private` members | Not a smell |
| Fence Post | `#pragma region`, banner comments | `#region`, banner comments | `# ====` banners |
| Breadcrumb | `} // namespace` included | `} // end class` | `# end for` |
| Prose Attribute | `[[deprecated]]`, `[[nodiscard]]` | `[Obsolete]`, attributes | `warnings.warn`, `@deprecated`, `typing.final` |

---

# Severity guidance for review tooling

**Mechanical** (a pattern can catch it; flag every time):
Sticky Note, Zombie Code, Ship's Log, Autograph, Fence Post, Breadcrumb, Costume, Prose Attribute, Price Tag, Echo (summary text ≈ member name), Long Parameter List (count), Long Function (length), Dead Code (unreferenced), Repeated Switches (same discriminant in N places).

**Judgment** (model reads the code):
All other code smells; Subtitles, Deodorant, Empty Theater, Liar, Ghost Reference, Gossip, Mumble, Uniform, Encyclopedia, Riddle, and whether an Amplifier names its failure.
