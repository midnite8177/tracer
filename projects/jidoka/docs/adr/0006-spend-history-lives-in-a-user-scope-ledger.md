# 0006 — Spend history lives in a user-scope ledger

Jeff wants to see what each epic cost and to compare costs as he changes
models and effort, across repos and over months. Beads cannot hold that
history well. A repo's beads are stealth and local to it, and a row for
every worker run would swell the task beads. So jidoka appends one row
per worker run to a SQLite ledger in its user-scope data folder, priced
in dollars when written, and tracer-ui reads the ledger without writing
to it. The epic's running total also goes into the epic's metadata,
because the scheduler reads only beads when it checks the budget. ADR
0003 rejected a second store for holdouts partly because such a store
outlives the epics it serves. Spend history has to outlive them. A
database owned by tracer-ui was the alternative, and it would tie the
factory to tracer-ui's schema, while ADR 0004 keeps the factory free of
tracer-ui.
