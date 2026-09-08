# 0002 — One app per machine, with a registry in the user configuration directory

The person works in several repositories, so the app could run once per
repository and read the `.beads/` directory beside it. Instead one copy
runs per machine and holds a registry of project paths, because a separate
process and port per repository makes the person start a tool before every
piece of work, and it makes a view across projects impossible. The
registry lives in the user configuration directory, not in any repository,
so that no repository carries a personal list of the other repositories.
