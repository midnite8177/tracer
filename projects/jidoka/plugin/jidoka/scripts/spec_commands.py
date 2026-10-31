"""The command lines that run an app's acceptance specs: all of them, or one by name.

An app's spec_command runs every spec, and its spec_target follows it to run one, with one <...> placeholder for the
spec's name. run_specs.py runs these lines for a worker and the scheduler, and the merge gate runs them for the spec
task's lap.
"""
from __future__ import annotations

import settings_reader
import target_placeholder


class SpecCommandError(Exception):
    """A reason an app has no command line for its specs, worded for the person who reads stderr."""


def spec_commands(app: settings_reader.App) -> tuple[str, str | None]:
    """The app's spec_command and spec_target; raises SpecCommandError, saying what to do, for an app with no
    acceptance folder or no spec command."""
    if app.acceptance is None:
        raise SpecCommandError(f"{app.name!r} has no acceptance folder, so it has no specs to run. Run "
                               "/jidoka:onboard to record the folder of its acceptance specs")
    if app.spec_command is None:
        raise SpecCommandError(f"{app.name!r} has an acceptance folder but no spec command. Run /jidoka:onboard to "
                               "record the command that runs its specs and how to target one")
    return app.spec_command, app.spec_target


def command_for_one(app: settings_reader.App, command: str, target: str | None, spec: str) -> str:
    """The command line that runs the one spec, its name quoted for the shell."""
    if target is None:
        raise SpecCommandError(f"{app.name!r} has a spec command but does not say how to target a spec. "
                               "Run /jidoka:onboard to record it")
    count = len(target_placeholder.PLACEHOLDER.findall(target))
    if count != 1:
        raise SpecCommandError(f"the spec_target of app {app.name!r} is {target!r}, which needs exactly one <...> "
                               f"placeholder for the spec's name and has {count}")
    return f"{command} {target_placeholder.filled(target, spec)}"
