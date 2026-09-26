# Adopt notes: Campfire, seed r30 → r34 (2026-09-26)

Same pin (`v1.2.3`), so no upstream fetch. Ordered by cost.

1. **Step 6b contradicts the r32 changelog on `migrate`.** 6b says a
   directory the manifest does not name is "reported, not deleted"; r32
   says `migrate` was removed. The adopter deleted it (backup kept
   outside the repo) because the guide's routing line for it goes in the
   same revision and a stale `/tracer:migrate` would still show in the
   plugin. Suggest 6b name seed-retired directories explicitly as
   "delete", keeping "report, don't delete" for unknown ones.
2. **The diff between the parked `docs/tracer.md` and the new seed is the
   fastest re-adopt path.** Every r31–34 change was a hunk in that diff;
   the changelog was confirmation, not the map. Worth saying in step 14.
3. Block-by-block diff results: Block 1, Block 2 (after the Delegating
   bullet), Block 4, 4b, 4c, 4d (after the `show-me-your-work`
   description), 4e and the status line all matched byte for byte.
   P1 body rebuilt from the blockquote; P4 body still matches; P2, P3,
   P5–P8 anchors all present. `claude plugin validate` passed;
   `issues.py --doctor` and the board rendered; `budget.py` ran.
4. Budget: `implement` is now 203 lines (over the 200-line ⚠ mark) after
   r32–34 grew the build phase. Not a problem, but the seed's own skill
   now trips the seed's own threshold.
