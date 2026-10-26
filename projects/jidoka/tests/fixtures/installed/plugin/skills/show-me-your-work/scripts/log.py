#!/usr/bin/env python3
"""Append a well-formed row to a show-me-your-work decision log (TSV).
Usage: log.py <logfile> <phase> <decision> <why> <evidence> <result>
Portable replacement for upstream's log.sh; same behavior, same output."""
import os, sys
from datetime import datetime, timezone

if len(sys.argv) != 7:
    sys.stderr.write("usage: log.py <logfile> <phase> <decision> <why> <evidence> <result>\n"); sys.exit(1)

logfile, cells = sys.argv[1], sys.argv[2:]
d = os.path.dirname(logfile)
if d and not os.path.isdir(d): os.makedirs(d, exist_ok=True)
if not os.path.isfile(logfile):
    with open(logfile, "w", encoding="utf-8", newline="\n") as fh: fh.write("ts\tphase\tdecision\twhy\tevidence\tresult\n")

def clean(v):
    # one line per cell; neutralize spreadsheet formula triggers, since reviewers open this in spreadsheets
    v = v.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v

ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(logfile, "a", encoding="utf-8", newline="\n") as fh:
    fh.write("\t".join([ts] + [clean(c) for c in cells]) + "\n")
