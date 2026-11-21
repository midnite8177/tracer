# 0011 — The scheduler reads an Antigravity account's usage from T3

ADR 0010 has the host read the account's usage windows, because a script
outside the host cannot ask. An Antigravity host under T3 has no lap mod
to do that reading, but T3 itself reads the account's quota from Google
with Antigravity's own sign-in and keeps it in its provider status. So on
each scheduler call a jidoka script asks T3's local server for that
status, over T3's own client protocol, with a read-only token that setup
issues once on the human's confirm, and writes the reading for the
scheduler. jidoka still never touches the Google login; T3 holds it.
Antigravity's quota comes in buckets, one per family of models, so the
reserve watches the bucket of the stage's model. The protocol is T3's
private one and can change with any T3 update, and T3 renews its reading
only while Antigravity takes turns. A failed or stale reading counts as
none, the scheduler holds nothing back, and the epic says so once. The
alternatives were no reserve at all for Antigravity, or a jidoka script
that calls Google with Antigravity's token, which would make jidoka
handle the human's login.
