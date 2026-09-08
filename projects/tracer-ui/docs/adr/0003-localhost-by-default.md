# 0003 — The app binds localhost, and LAN access is an explicit flag

The app binds the loopback interface, thus no other machine reaches it. A
person who wants the board on a phone passes a flag that binds every
interface instead. The flag adds no authentication and no transport
security, because a login for a single-person local tool costs more than
it returns; the mode is therefore for a trusted network only, and the
default stays closed so that a backlog is never exposed by accident.
