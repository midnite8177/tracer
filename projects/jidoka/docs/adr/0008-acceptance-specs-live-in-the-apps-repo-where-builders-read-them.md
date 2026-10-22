# 0008 — Acceptance specs live in the app's repo, where builders read them

Holdouts are hidden from every builder, so acceptance specs looked as if
they should be hidden too. They are not. An acceptance spec is the target
a builder works toward, and Farley's method has the builder run it red
before it writes code and green before it merges. A builder that cannot
read its target cannot do either. The specs, the code beneath them and the
protocol driver sit in an acceptance folder in the app's repo, committed
like any other test project. They are the app's tests, not jidoka's
machinery, so ADR 0007 still holds: nothing in the folder names jidoka,
and the folder's path lives in the app's entry in `~/.jidoka/`. What keeps
a builder from weakening a spec to reach green is that it cannot write
there. The lap mod refuses Write and Edit in the folder to every lap
worker except the spec task's, and the merge gate refuses any other lap
whose diff touches it, which also covers changes made through Bash. A
builder that thinks a spec is wrong parks its task and asks, because
changing a spec changes the contract and only the human does that.
Holdouts keep the job of catching what the specs leave out.
