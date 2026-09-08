# 0001 — One directory per project

This repository will hold several projects, and tracer-ui is the first.
Each project therefore lives in `projects/<name>/` with its own solution
file, its own source projects and its own test project, instead of one
solution at the repository root. This keeps the projects independent and
makes shared code a deliberate act, at the cost of easy reuse between
them.
