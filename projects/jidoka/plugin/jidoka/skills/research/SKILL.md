---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
license: MIT
metadata:
  upstream: "https://github.com/mattpocock/skills#skills/engineering/research"
  upstream-base: "24fe0ef7737efae15c87225755e9f6f5965e4888"
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.

Add this to the delegated agent's instructions, with `<skill folder>` replaced by the directory that holds this SKILL.md: "You are the research agent. Do not invoke research or spawn further agents; do the reading yourself and write the file. Before writing it, read `<skill folder>/../unslop/SKILL.md` and apply it."
