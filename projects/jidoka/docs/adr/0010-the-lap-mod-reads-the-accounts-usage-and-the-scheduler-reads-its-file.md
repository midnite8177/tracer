# 0010 — The lap mod reads the account's usage, and the scheduler reads its file

Only the host knows how much of its usage windows the account has used. A
script that the launcher runs sits outside the host and cannot ask. So the
lap mod asks the host each time the manager calls the scheduler, and writes
the windows to a file in jidoka's home. The scheduler, which ADR 0002 makes
the one that decides, reads that file and applies the reserves. The reading
stays out of the epic's beads because the human may change the account at
any time, and a stored reading would outlive the account it came from. A
reading older than ten minutes counts as none, so a host without the lap mod
holds nothing back. Having the scheduler call the usage endpoint itself was
the alternative. It would make jidoka handle the human's login, and the
account is the human's to choose.
