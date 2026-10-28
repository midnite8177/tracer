"""What the scheduler does with a lap when its worker's stage ends.

Each function takes one way a stage ended, such as a failed build, a Spec check that sent the diff back or a
finished build, and returns the laps that go back to a worker: an empty list when the lap parked, blocked or
merged. The scheduler picks the function from the worker's outcome and prints the next moves after it. Everything
these functions write on a lap they write with BEADS_ACTOR set to jidoka, and the output of the tests and the gate
goes to stderr.

The outcomes of a worker's stage, for a task on the simple track, whose lap starts at the build:
  done       the build finished, with the app and the filter the builder named, which are recorded on the task. The
             scheduler stages everything the build left in the lap's worktree, apart from the scratch folder, and
             commits it as one commit whose message is the task's title, under the repo's git user; a build that left
             no changes makes no commit. It runs that app's targeted tests with that filter, through
             targeted_tests.py, on the lap's head rebased onto the epic branch, and again after a fresh rebase when
             the epic branch moved during the run. A pass goes to the merge gate, merge_gate.py. When the gate finds
             the epic branch moved since the run, the tests run again, and that is not a try. A `done` also files the
             discovered work placed `epic` and `outside` before it commits, and a `blocks` finding on a `done` is a
             try.
  failed     the worker failed. `--why` carries the worker's own reason into the try's comment and the park's.
  cut off    the worker ended for a reason outside its work; the lap goes back to the stage, and that is not a try.
             A stage that runs past its wall clock ends cut off whatever the worker reported. The cutoff that reaches
             caps.CUTOFF_CAP parks the task.
  send back  a check sent the lap's diff back to the build. It is not a try; the send-back that reaches
             caps.SEND_BACK_CAP, from the checks together, parks the task.
  question   the worker needs a decision. The worker left a question report in the lap's scratch folder, and park.py
             posts it on the task and parks the task. The lap keeps its tries, and its slot and area are free for the
             next ready task. A missing or unusable report is a try instead.
  blocked    the worker cannot finish without work it discovered. It left a discovered-work report in the lap's
             scratch folder, and discovered.py files each finding, linked discovered-from to the task, and ends the
             lap blocked. A missing or unusable report, or one with no `blocks` finding, is a try instead.

A failed worker, a red targeted run, a filter the targeted tests refuse or that runs no tests, and a lap the merge
gate finds with no commit the epic branch lacks are each a try: `lap.tries` goes up by one, a comment says why, and
the lap goes back to the stage. The try that reaches caps.TRY_CAP parks the task. The failure that reaches
TEST_FAILURES_TO_MOVE in a simple lap's own build, counted in `lap.testfailures`, also sets `lap.track` to `full` and
posts a comment that begins `Moved to the full track` and names the evidence. No other cause moves a task, and a full
task never moves back. Every cap that parks a task names itself in the comment. A refusal of the merge gate parks the
task too, naming its check. A parked task has `lap.stage` parked, status open, no assignee, the human label and a
comment saying why; its worktree and branch stay, and its slot and area are free.

A task on the full track has more stages: the research brief (`research`), the build, the targeted tests, the app check
(`app-check`, only when a holdout names the task), the Spec check (`spec-check`), then the merge gate.
  research   `done` posts the brief the worker left in `research-brief.md` in the scratch folder on the task as a
             `research brief:` comment and sends the lap to the build. A missing or empty brief is a try of the
             research.
  build      a `done` runs the targeted tests as above. A pass sends the lap, with a comment, to the app check when a
             holdout names the task, and else to the Spec check, instead of the merge gate.
  app-check  the worker reads the holdouts that name the task, runs the app on the lap's slot and tests it from
             outside, and leaves `app-check.json` in the scratch folder, as app_check.py describes. Every holdout
             green sends the lap to the Spec check. A red one sends the lap back to the build with no try, with the
             holdout's number, its verdict and what a user saw, never a step. A report that is missing or unusable is
             a try of the app check.
  spec-check the worker left its outcome block in `spec-check.json` in the scratch folder, and the report names the
             outcome. `pass` sends the lap to the merge gate with the targeted run it holds; the tests run again only
             when the epic branch moved since, and the lap goes back to the build when they then fail. `send back`
             posts the block's findings on the task, keeps them in `lap.findings` and sends the lap to the build,
             with no try. `cannot judge` parks the task with the block's reason, and no try is counted. A block that
             is missing or unusable is a try of the Spec check. Any `done` there is refused.

Newer work on the epic branch calls the merge worker instead of counting a try: a conflict while rebasing the lap onto
the epic branch, naming the files, or targeted tests that fail on a lap the rebase brought newer work into. The lap
goes to the stage `merge` with a comment, its tries unchanged, and `lap.mergewhy` and `lap.mergebase` (the epic
branch's head then) in the task's metadata. The merge worker rebases the lap onto the epic branch in the lap's
worktree, resolves the conflicts, and fixes what the merge broke. A report on a lap at the merge takes the outcomes of
the build, with these differences. `done` means the worker reconciled the lap: a worktree left in the middle of a
rebase, or a lap head that lacks `lap.mergebase`, is a merge try; otherwise the scheduler folds what the worker left
into the lap's own commit and runs the targeted tests and the merge gate as for a build, and a conflict or red tests
that newer work causes again call the merge worker, with no try. `failed` is a merge try. A merge try raises
`lap.mergetries` by one and calls the merge worker again; the one that reaches caps.MERGE_TRY_CAP parks the task.
"""
from __future__ import annotations

import contextlib
import dataclasses
import sys
from pathlib import Path

import app_check
import caps
import discovered
import holdouts
import lap_record
import merge_gate
import park
import spec_check
import targeted_tests
from commands import SCRATCH_FOLDER, CommandError, capture, env_as_factory, head_of, run
from lap_record import APP_CHECK, BLOCKED_OUTCOME, BRIEF_PREFIX, BUILD, DONE, FULL_TRACK, MERGE, SPEC_CHECK, \
    GateContext, Lap, SchedulerError, words
from park import HUMAN_LABEL

RESEARCH_BRIEF = "research-brief.md"
TEST_FAILURES_TO_MOVE = 2
NOTHING_STAGED = 0
CHANGES_STAGED = 1


def park_lap(lap: Lap, epic: str, tries: int, why: str, main_tree: Path) -> None:
    """Ends the lap parked: the task waits on the human, open and unassigned, with its worktree and branch kept.

    The parked lap counts toward the epic's brake.
    """
    park.park(lap.task, tries, f"{park.PARKED_PREFIX}{why}. The worktree {lap.worktree} and the branch {lap.branch} "
                               f"keep the work. Take the {HUMAN_LABEL} label off to give the task a new lap.", [],
              main_tree)
    caps.note_parked_lap(epic, lap.stage, main_tree)


def ask(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Parks the task on the question the worker left; a report that cannot be posted counts a try."""
    try:
        park.park_on_question(lap.task, lap.tries, lap.scratch, lap.worktree, lap.branch, main_tree)
    except park.QuestionError as error:
        return count_try(lap, epic, f"the question could not be posted: {error}", main_tree)
    return []


def block(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Files the discovered work the lap cannot finish without and ends the lap blocked on it.

    A report that is missing, unusable or names no blocking finding counts a try of the stage instead.
    """
    try:
        findings = discovered.read_findings(lap.scratch)
        blockers = discovered.blockers_in(findings)
        if not blockers:
            raise discovered.DiscoveryError(f"the {BLOCKED_OUTCOME} outcome needs a finding in "
                                            f"{discovered.DISCOVERED_REPORT} whose placement is {discovered.BLOCKS}")
        filed = discovered.file_findings(findings, lap.task, lap.area, epic, main_tree)
    except discovered.DiscoveryError as error:
        return count_try(lap, epic, f"the discovered work could not be filed: {error}", main_tree)
    discovered.block(lap.task, lap.tries, [item for item in filed if item.finding.placement == discovered.BLOCKS],
                     lap.worktree, lap.branch, main_tree)
    discovered.clear_report(lap.scratch)
    return []


def file_discovered_work(lap: Lap, epic: str, main_tree: Path) -> str | None:
    """Files the discovered work a finished stage reported; returns why it could not, or None.

    A finished stage has nothing it cannot finish without, so a finding that blocks the task is refused.
    """
    try:
        findings = discovered.read_findings(lap.scratch)
        if discovered.blockers_in(findings):
            raise discovered.DiscoveryError(f"a {DONE} stage has no finding whose placement is {discovered.BLOCKS}. "
                                            f"End {BLOCKED_OUTCOME} instead")
        discovered.file_findings(findings, lap.task, lap.area, epic, main_tree)
    except discovered.DiscoveryError as error:
        return f"the discovered work could not be filed: {error}"
    discovered.clear_report(lap.scratch)
    return None


def count_try(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a failed try of the stage the lap is at: a try of the merge worker at the merge, else a try of the lap.

    Each stage's own cap is the one that reaches the park, as _count_lap_try and count_merge_try say.
    """
    if lap.stage == MERGE:
        return count_merge_try(lap, epic, why, main_tree)
    return _count_lap_try(lap, epic, why, main_tree)


def _count_lap_try(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a failed try of the lap. The try that reaches caps.TRY_CAP parks the task; an earlier one sends the lap
    back to the stage."""
    tries = lap.tries + 1
    name = words(lap.stage)
    cap = lap_record.try_cap(lap.stage)
    if tries >= cap:
        park_lap(lap, epic, tries, f"the try cap of {cap} is reached: {name} try {tries} of {cap} "
                                   f"failed: {why}", main_tree)
        return []
    env = env_as_factory()
    run(["bd", "comment", lap.task,
         f"{name[:1].upper()}{name[1:]} try {tries} of {cap} failed: {why}. The lap goes back to the "
         f"{name}."], main_tree, env)
    run(["bd", "update", lap.task, *lap_record.counting_tries(tries), *lap_record.entering(lap.stage)], main_tree,
        env)
    return [dataclasses.replace(lap, tries=tries)]


def cut_off(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a cutoff of the stage. The cutoff that reaches caps.CUTOFF_CAP parks the task; an earlier one reruns the
    stage, and no try is counted."""
    cutoffs = lap.cutoffs + 1
    if cutoffs >= caps.CUTOFF_CAP:
        park_lap(lap, epic, lap.tries, f"the cutoff cap of {caps.CUTOFF_CAP} is reached: the {lap.stage} was cut off "
                                       f"{cutoffs} of {caps.CUTOFF_CAP} times, the last time because {why}",
                 main_tree)
        return []
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"The {lap.stage} was cut off, cutoff {cutoffs} of {caps.CUTOFF_CAP}, because "
                                    f"{why}. The lap goes back to the {lap.stage} and no try is counted."],
        main_tree, env)
    run(["bd", "update", lap.task, *lap_record.counting_cutoffs(lap.stage, cutoffs)], main_tree, env)
    return [dataclasses.replace(lap, cutoffs=cutoffs)]


def send_back(lap: Lap, epic: str, findings: list[spec_check.Finding], failed_holdouts: list[app_check.Verdict],
              main_tree: Path) -> list[Lap]:
    """Counts a send-back from the checks. The cap's last one parks the task; an earlier one reruns the build.

    A Spec check's findings, and the holdouts the app check saw fail, go on the task as a comment and in its
    metadata, where the next build reads them. A failed holdout is kept as its number, its verdict and what a user
    saw, never its steps.
    """
    send_backs = lap.send_backs + 1
    if send_backs >= caps.SEND_BACK_CAP:
        park_lap(lap, epic, lap.tries, f"the send-back cap of {caps.SEND_BACK_CAP} is reached: the checks sent the "
                                       f"diff back {send_backs} of {caps.SEND_BACK_CAP} times"
                                       + findings_in_words(findings, failed_holdouts), main_tree)
        return []
    stage = BUILD if lap.stage in (SPEC_CHECK, APP_CHECK) else lap.stage
    spec_json = spec_check.as_json(findings) if findings else ""
    app_json = app_check.as_json(failed_holdouts) if failed_holdouts else ""
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"The checks sent the diff back, send-back {send_backs} of "
                                    f"{caps.SEND_BACK_CAP}. The lap goes back to the {stage} and no try is "
                                    f"counted.{findings_in_words(findings, failed_holdouts)}"], main_tree, env)
    run(["bd", "update", lap.task, *lap_record.counting_send_backs(send_backs), *lap_record.entering(stage),
         *lap_record.recording_findings(spec_json, app_json)], main_tree, env)
    return [dataclasses.replace(lap, stage=stage, send_backs=send_backs, spec_passed=False, findings=spec_json,
                                app_findings=app_json)]


def findings_in_words(findings: list[spec_check.Finding], failed_holdouts: list[app_check.Verdict]) -> str:
    spec = f"\nThe {words(SPEC_CHECK)}'s findings:\n{spec_check.describe(findings)}" if findings else ""
    app = f"\nThe {words(APP_CHECK)}'s findings:\n{app_check.describe(failed_holdouts)}" if failed_holdouts else ""
    return f"{spec}{app}"


def spec_check_sent_back(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Takes the Spec check's send back: its findings go to a new build. A block that is missing or unusable counts a
    try of the Spec check."""
    try:
        findings = spec_check.read_findings(lap.scratch)
    except spec_check.SpecCheckError as error:
        return count_try(lap, epic, f"the outcome block cannot be used: {error}", main_tree)
    spec_check.clear_report(lap.scratch)
    return send_back(lap, epic, findings, [], main_tree)


def spec_check_cannot_judge(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Takes the Spec check's cannot judge: the task parks with its reason, and no try is counted."""
    try:
        reason = spec_check.read_reason(lap.scratch)
    except spec_check.SpecCheckError as error:
        reason = f"it gave no usable reason ({error})"
    spec_check.clear_report(lap.scratch)
    park_lap(lap, epic, lap.tries, f"the {words(SPEC_CHECK)} cannot judge the diff: {reason}", main_tree)
    return []


def enter_stage(lap: Lap, stage: str, main_tree: Path) -> Lap:
    """Moves the lap to the stage and returns it; the stage's own cutoffs start at none for the lap's records."""
    run(["bd", "update", lap.task, *lap_record.entering(stage)], main_tree, env_as_factory())
    return dataclasses.replace(lap, stage=stage, cutoffs=caps.NONE_YET)


def research_done(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Posts the research brief the worker left in the scratch folder on the task and sends the lap to the build. A
    missing or empty brief counts a try of the research."""
    path = lap.scratch / RESEARCH_BRIEF
    try:
        brief = path.read_text(encoding="utf-8").strip()
    except OSError:
        brief = ""
    if not brief:
        return count_try(lap, epic, f"the research brief {path} is missing or empty", main_tree)
    run(["bd", "comment", lap.task, f"{BRIEF_PREFIX}{brief}"], main_tree, env_as_factory())
    path.unlink(missing_ok=True)
    return [enter_stage(lap, BUILD, main_tree)]


def start_spec_check(lap: Lap, main_tree: Path) -> list[Lap]:
    """Sends a full-track lap whose targeted tests passed to the Spec check, before the merge gate."""
    run(["bd", "comment", lap.task, f"The targeted tests passed. The lap goes to the {words(SPEC_CHECK)}, before "
                                    "the merge gate."], main_tree, env_as_factory())
    return [enter_stage(lap, SPEC_CHECK, main_tree)]


def start_checks(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Sends a full-track lap whose targeted tests passed to its first check: the app check when a holdout names its
    task, else the Spec check."""
    if not holdouts.numbered_naming(lap.task, holdouts.read(epic, main_tree)):
        return start_spec_check(lap, main_tree)
    run(["bd", "comment", lap.task, f"The targeted tests passed. The lap goes to the {words(APP_CHECK)}, then to "
                                    f"the {words(SPEC_CHECK)}, before the merge gate."], main_tree, env_as_factory())
    return [enter_stage(lap, APP_CHECK, main_tree)]


def app_check_done(lap: Lap, epic: str, main_tree: Path) -> list[Lap]:
    """Takes the app check's report: every holdout that names the task green sends the lap on to the Spec check, and
    a red one sends the diff back to the build with the holdout's number, its verdict and what a user saw. A report
    that is missing or unusable counts a try of the app check."""
    every_holdout = holdouts.read(epic, main_tree)
    try:
        verdicts = app_check.read_verdicts(lap.scratch, lap.task, every_holdout)
    except app_check.AppCheckError as error:
        return count_try(lap, epic, f"the report cannot be used: {error}", main_tree)
    app_check.clear_report(lap.scratch)
    failed = [verdict for verdict in verdicts if not verdict.passed]
    if failed:
        return send_back(lap, epic, [], failed, main_tree)
    return start_spec_check(lap, main_tree)


def spec_check_passed(lap: Lap, context: GateContext) -> list[Lap]:
    """Takes the Spec check's pass: the lap goes to the merge gate with the targeted run it already has.

    The tests run again only when the epic branch moved since that run. The lap returns to the build when they then
    fail, so the build's try count and its stage are what a red run counts against.
    """
    building = dataclasses.replace(lap, stage=BUILD, spec_passed=True)
    if not (lap.app and lap.test_filter):
        return count_try(building, context.epic, "the lap records no app and filter for its targeted tests",
                         context.main_tree)
    run(["bd", "comment", lap.task, f"The {words(SPEC_CHECK)} passed: the diff does what the task says, and nothing "
                                    "more."], context.main_tree, env_as_factory())
    run(["bd", "update", lap.task, *lap_record.passing_spec_check()], context.main_tree, env_as_factory())
    spec_check.clear_report(lap.scratch)
    return through_the_gate(building, context)


def stage_work(lap: Lap) -> bool:
    """Stages everything a worker left in the lap's worktree outside the scratch folder; True when any change is
    staged."""
    env = env_as_factory()
    run(["git", "add", "--all"], lap.worktree, env)
    run(["git", "reset", "--quiet", "--", SCRATCH_FOLDER], lap.worktree, env)
    staged = capture(["git", "diff", "--cached", "--quiet"], lap.worktree, env)
    if staged.returncode not in (NOTHING_STAGED, CHANGES_STAGED):
        raise CommandError(f"git diff --cached failed in {lap.worktree}: {staged.stderr.strip()}")
    return staged.returncode == CHANGES_STAGED


def commit_build(lap: Lap) -> None:
    """Commits what the build left in the lap's worktree, outside the scratch folder, under the task's title."""
    if stage_work(lap):
        run(["git", "commit", "--quiet", "--message", lap.title], lap.worktree, env_as_factory())


def commit_reconciliation(lap: Lap, epic_branch: str) -> None:
    """Folds what the merge worker left into the lap's own commit, so the epic branch keeps one commit per task.

    A lap with no commit of its own gets a commit under the task's title instead.
    """
    own = run(["git", "rev-list", f"refs/heads/{epic_branch}..HEAD"], lap.worktree, None).split()
    if not own:
        commit_build(lap)
    elif stage_work(lap):
        run(["git", "commit", "--quiet", "--amend", "--no-edit"], lap.worktree, env_as_factory())


def rebase_unfinished(lap: Lap) -> bool:
    """True when the lap's worktree is off the lap branch, as it is in the middle of a rebase."""
    return merge_gate.checked_out_branch(lap.worktree) != lap.branch


def abandon_rebase(lap: Lap) -> None:
    """Puts a worktree whose rebase a worker left unfinished back on the lap branch as it was."""
    if rebase_unfinished(lap):
        capture(["git", "rebase", "--abort"], lap.worktree, env_as_factory())


def count_merge_try(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a failed try of the merge worker. The try that reaches caps.MERGE_TRY_CAP parks the task; an earlier one
    calls the worker again."""
    abandon_rebase(lap)
    tries = lap.merge_tries + 1
    cap = lap_record.try_cap(MERGE)
    if tries >= cap:
        park_lap(lap, epic, lap.tries, f"the merge try cap of {cap} is reached: merge try {tries} of "
                                       f"{cap} failed: {why}", main_tree)
        return []
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"Merge try {tries} of {cap} failed: {why}. The lap goes back to "
                                    f"the {MERGE} worker."], main_tree, env)
    run(["bd", "update", lap.task, *lap_record.counting_merge_tries(tries)], main_tree, env)
    return [dataclasses.replace(lap, merge_tries=tries)]


def call_merge_worker(lap: Lap, epic_branch: str, why: str, main_tree: Path) -> list[Lap]:
    """Sends the lap to the merge worker, which reconciles it with newer work on the epic branch. No try is counted.

    The lap records the epic branch's head as of the call, which a reconciled lap must hold.
    """
    base = head_of(f"refs/heads/{epic_branch}", main_tree) or ""
    env = env_as_factory()
    run(["bd", "comment", lap.task, f"Merge worker called: {why}. The lap goes to the {MERGE} stage and no try is "
                                    "counted."], main_tree, env)
    run(["bd", "update", lap.task, *lap_record.calling_merge_worker(why, base)], main_tree, env)
    cutoffs = lap.cutoffs if lap.stage == MERGE else caps.NONE_YET
    return [dataclasses.replace(lap, stage=MERGE, cutoffs=cutoffs, merge_why=why, merge_base=base)]


def brings_newer_work(lap: Lap, epic_branch: str, main_tree: Path) -> bool:
    """True when the epic branch holds a commit the lap's head lacks, so the targeted tests rebase it in."""
    epic_head = head_of(f"refs/heads/{epic_branch}", main_tree)
    lap_head = head_of(f"refs/heads/{lap.branch}", main_tree)
    return epic_head is not None and lap_head is not None and not merge_gate.contains(epic_head, lap_head, main_tree)


def reconciled(lap: Lap, context: GateContext) -> list[Lap]:
    """Takes the merge worker's done: its work joins the lap's commit and the lap goes through the targeted tests and
    the gate again."""
    if rebase_unfinished(lap):
        return count_merge_try(lap, context.epic, "the merge worker left the rebase unfinished", context.main_tree)
    lap_head = head_of(f"refs/heads/{lap.branch}", context.main_tree)
    if lap.merge_base and (lap_head is None
                           or not merge_gate.contains(lap.merge_base, lap_head, context.main_tree)):
        return count_merge_try(lap, context.epic, f"the lap does not hold {context.epic_branch} at "
                                                  f"{lap.merge_base}, so the merge worker reconciled nothing",
                               context.main_tree)
    commit_reconciliation(lap, context.epic_branch)
    return through_the_tests(lap, context)


def count_red_tests(lap: Lap, epic: str, why: str, main_tree: Path) -> list[Lap]:
    """Counts a red targeted run of the lap's own build as a try. The failure that reaches TEST_FAILURES_TO_MOVE in a
    simple lap moves the task to the full track, with a comment that names the evidence; a task on the full track
    never moves back, and nothing else moves a task."""
    if lap.stage != BUILD or lap.track == FULL_TRACK:
        return count_try(lap, epic, why, main_tree)
    failures = lap.test_failures + 1
    env = env_as_factory()
    run(["bd", "update", lap.task, *lap_record.counting_test_failures(failures)], main_tree, env)
    lap = dataclasses.replace(lap, test_failures=failures)
    if failures >= TEST_FAILURES_TO_MOVE:
        run(["bd", "comment", lap.task, f"Moved to the full track: the targeted tests failed twice in this simple "
                                        f"lap, the last time because {why}."], main_tree, env)
        run(["bd", "update", lap.task, *lap_record.moving_to_full_track()], main_tree, env)
        lap = dataclasses.replace(lap, track=FULL_TRACK)
    return count_try(lap, epic, why, main_tree)


def name_tests(lap: Lap, app: str, test_filter: str, main_tree: Path) -> Lap:
    """Records the app and the filter the worker named for the lap's targeted tests on the task, and returns the lap
    that holds them. The merge gate and a Spec check pass read them from the lap."""
    run(["bd", "update", lap.task, *lap_record.naming_tests(app, test_filter)], main_tree, env_as_factory())
    return dataclasses.replace(lap, app=app, test_filter=test_filter)


def targeted_run_sends_away(lap: Lap, context: GateContext) -> list[Lap] | None:
    """Runs the lap's targeted tests, rebased onto the epic branch; returns the laps that go back to a worker when the
    run sends the lap away from the gate, and None when the lap goes on.

    A conflict rebasing onto newer work on the epic branch, or tests that fail once that work is in, call the merge
    worker and count no try. A full-track lap whose tests pass goes to the checks first, unless it has passed them.
    """
    newer_work = brings_newer_work(lap, context.epic_branch, context.main_tree)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            tested = targeted_tests.targeted_tests(lap.task, lap.worktree, context.epic_branch,
                                                   targeted_tests.Integration.REBASE, lap.app, lap.test_filter,
                                                   context.home, env_as_factory())
    except targeted_tests.MergeConflict as conflict:
        return call_merge_worker(lap, context.epic_branch, f"rebasing the lap onto {context.epic_branch} conflicts "
                                                           f"in {', '.join(conflict.files)}", context.main_tree)
    except targeted_tests.FilterRefused as refused:
        return count_try(lap, context.epic, f"the filter needs fixing: {refused}", context.main_tree)
    except targeted_tests.TestRunError as error:
        raise SchedulerError(f"the targeted tests of {lap.task} did not run: {error}") from error
    if not tested.passed:
        why = f"the targeted tests failed with exit code {tested.exit_code}"
        if newer_work:
            return call_merge_worker(lap, context.epic_branch,
                                     f"{why} once newer work on {context.epic_branch} was merged in",
                                     context.main_tree)
        return count_red_tests(lap, context.epic, why, context.main_tree)
    if lap.track == FULL_TRACK and not lap.spec_passed:
        return start_checks(lap, context.epic, context.main_tree)
    return None


def merge_attempt(lap: Lap, context: GateContext) -> list[Lap] | None:
    """Merges the lap into the epic branch through the merge gate; returns the laps that go back to a worker, an empty
    list when the lap merged or parked, and None when the epic branch moved since the tests ran."""
    try:
        with contextlib.redirect_stdout(sys.stderr):
            merged = merge_gate.merge(merge_gate.LapToMerge(lap.task, lap.branch, lap.worktree, context.epic_branch),
                                      context.settings, context.home, context.main_tree)
    except merge_gate.EpicBranchMoved as moved:
        print(f"scheduler: {moved}, so the targeted tests run again", file=sys.stderr)
        return None
    except merge_gate.EmptyLap as empty:
        return count_try(lap, context.epic, str(empty), context.main_tree)
    except merge_gate.GateRefused as refused:
        park_lap(lap, context.epic, lap.tries, f"the merge gate refused the lap: {refused}", context.main_tree)
        return []
    if merged.failed_steps:
        raise SchedulerError(f"{context.epic_branch} has the lap's commit {merged.sha}, but these steps failed:\n"
                             + "\n".join(f"  {step}" for step in merged.failed_steps))
    caps.note_merge(context.epic, context.main_tree)
    return []


def through_the_gate(lap: Lap, context: GateContext) -> list[Lap]:
    """Merges a lap that holds a passing targeted run, and retries until the epic branch holds still.

    When the epic branch moved since that run, the tests run again before the next attempt. Returns the laps that go
    back to a worker.
    """
    while True:
        settled = merge_attempt(lap, context)
        if settled is not None:
            return settled
        settled = targeted_run_sends_away(lap, context)
        if settled is not None:
            return settled


def through_the_tests(lap: Lap, context: GateContext) -> list[Lap]:
    """Runs the lap's targeted tests and, when they pass, takes the lap on to the merge gate or to the checks; returns
    the laps that go back to a worker."""
    settled = targeted_run_sends_away(lap, context)
    return through_the_gate(lap, context) if settled is None else settled


def build_done(lap: Lap, context: GateContext) -> list[Lap]:
    """Takes a finished build: files its discovered work, commits what it left, and sends the lap through the
    targeted tests. A full-track lap starts with no Spec check result, because the build changed the diff."""
    unfiled = file_discovered_work(lap, context.epic, context.main_tree)
    if unfiled is not None:
        return count_try(lap, context.epic, unfiled, context.main_tree)
    commit_build(lap)
    if lap.track == FULL_TRACK:
        run(["bd", "update", lap.task, *lap_record.recording_findings("", "")], context.main_tree, env_as_factory())
        lap = dataclasses.replace(lap, spec_passed=False, findings="", app_findings="")
    return through_the_tests(lap, context)
