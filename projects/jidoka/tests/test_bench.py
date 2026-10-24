import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

PLUGIN = fixture.PROJECT / "plugin" / "jidoka"
LAUNCHER = PLUGIN / "bin" / "jidoka-run"
BENCH = PLUGIN / "scripts" / "bench.py"

RUN_TIMEOUT_SECONDS = 120
JEFF = "Jeff Bench"


def git(repo: Path, *args: str) -> str:
    return fixture.run(["git", *args], repo).strip()


class BenchCase(unittest.TestCase):
    """The shop repo and the helpers of the bench script tests; each subclass sets up its own."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.home = cls.root / "jidoka-home"
        cls.home.mkdir()
        (cls.home / "python").write_text(sys.executable + "\n", encoding="utf-8")

        cls.repo = cls.root / "shop"
        fixture.init_repo(cls.repo)
        git(cls.repo, "config", "user.name", JEFF)
        (cls.repo / "README.md").write_text("shop\n", encoding="utf-8")
        fixture.git_commit_all(cls.repo, "Start")
        git(cls.repo, "branch", "-M", "main")
        cls.bd = fixture.real_tool("bd")
        fixture.add_stealth_beads(cls.repo)
        cls.count = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def new_bead(self, kind: str) -> str:
        type(self).count += 1
        created = json.loads(fixture.run([self.bd, "create", "--title", f"Print the receipt {self.count}!",
                                          f"--type={kind}", "--json"], self.repo))
        return created["id"]

    def new_task_under(self, epic: str) -> str:
        type(self).count += 1
        created = json.loads(fixture.run([self.bd, "create", "--title", f"Print the receipt {self.count}!",
                                          "--type=task", "--parent", epic, "--json"], self.repo))
        return created["id"]

    def caller_env(self) -> dict[str, str]:
        return {**os.environ, "JIDOKA_HOME": str(self.home), "BEADS_ACTOR": "claude"}

    def bench(self, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(LAUNCHER), str(BENCH), *args], capture_output=True, text=True,
                              encoding="utf-8", timeout=RUN_TIMEOUT_SECONDS, env=env, cwd=self.repo)

    def shown(self, bead: str) -> dict:
        return json.loads(fixture.run([self.bd, "show", bead, "--json"], self.repo))[0]

    def comments(self, bead: str) -> list[dict]:
        return json.loads(fixture.run([self.bd, "comments", bead, "--json"], self.repo) or "[]") or []


class BenchStartTests(BenchCase):
    def test_starting_bench_work_assigns_the_bead_to_the_git_user_by_name_and_posts_a_start_comment(self):
        bead = self.new_bead("task")

        done = self.bench(self.caller_env(), "start", bead)

        self.assertEqual(0, done.returncode, done.stderr)
        shown = self.shown(bead)
        self.assertEqual(JEFF, shown.get("assignee"))
        self.assertEqual("in_progress", shown["status"])
        main = git(self.repo, "rev-parse", "main")
        branch = f"bench/print-the-receipt-{self.count}"
        self.assertEqual([f"bench started at {main} on {branch}"], [c["text"] for c in self.comments(bead)])
        self.assertEqual([JEFF], [c["author"] for c in self.comments(bead)])

    def test_the_worktree_sits_on_a_bench_branch_cut_from_main_and_stays_out_of_the_main_checkouts_status(self):
        bead = self.new_bead("bug")

        done = self.bench(self.caller_env(), "start", bead)

        self.assertEqual(0, done.returncode, done.stderr)
        printed = json.loads(done.stdout)
        worktree = self.repo / ".worktrees" / f"print-the-receipt-{self.count}"
        self.assertEqual({"bead": bead, "branch": f"bench/print-the-receipt-{self.count}",
                          "worktree": str(worktree), "start": git(self.repo, "rev-parse", "main")}, printed)
        self.assertEqual(printed["branch"], git(worktree, "rev-parse", "--abbrev-ref", "HEAD"))
        self.assertEqual(git(self.repo, "rev-parse", "main"), git(worktree, "rev-parse", "HEAD"))
        self.assertNotIn(bead, printed["branch"] + printed["worktree"])
        self.assertEqual("", git(self.repo, "status", "--porcelain", "--untracked-files=all"))

    def test_a_second_start_without_a_release_reuses_the_workspace_and_keeps_the_assignee(self):
        bead = self.new_bead("task")
        first = self.bench(self.caller_env(), "start", bead)
        self.assertEqual(0, first.returncode, first.stderr)

        done = self.bench(self.caller_env(), "start", bead)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(json.loads(first.stdout), json.loads(done.stdout))
        self.assertEqual(JEFF, self.shown(bead).get("assignee"))

    def test_start_takes_a_task_under_an_epic_the_factory_does_not_hold(self):
        epic = self.new_bead("epic")
        bead = self.new_task_under(epic)

        done = self.bench(self.caller_env(), "start", bead)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(JEFF, self.shown(bead).get("assignee"))


class BenchReleaseAndEndTests(BenchCase):
    def test_releasing_clears_the_assignee_and_keeps_the_worktree_and_its_commits(self):
        bead = self.new_bead("task")
        worktree = Path(json.loads(self.bench(self.caller_env(), "start", bead).stdout)["worktree"])
        (worktree / "receipt.txt").write_text("receipt\n", encoding="utf-8")
        fixture.git_commit_all(worktree, "Print the receipt")
        work = git(worktree, "rev-parse", "HEAD")

        done = self.bench(self.caller_env(), "release", bead)

        self.assertEqual(0, done.returncode, done.stderr)
        shown = self.shown(bead)
        self.assertEqual("open", shown["status"])
        self.assertEqual("", shown.get("assignee", ""))
        self.assertEqual(work, git(worktree, "rev-parse", "HEAD"))
        self.assertEqual(work, git(self.repo, "rev-parse", f"bench/print-the-receipt-{self.count}"))

    def test_a_start_after_a_release_reuses_the_worktree_and_hides_it_with_one_exclude_line(self):
        bead = self.new_bead("task")
        first = json.loads(self.bench(self.caller_env(), "start", bead).stdout)
        worktree = Path(first["worktree"])
        (worktree / "receipt.txt").write_text("receipt\n", encoding="utf-8")
        fixture.git_commit_all(worktree, "Print the receipt")
        work = git(worktree, "rev-parse", "HEAD")
        self.bench(self.caller_env(), "release", bead)
        (self.repo / "other.txt").write_text(f"other {self.count}\n", encoding="utf-8")
        fixture.git_commit_all(self.repo, "Move main on")

        done = self.bench(self.caller_env(), "start", bead)

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(first, json.loads(done.stdout))
        self.assertEqual(work, git(worktree, "rev-parse", "HEAD"))
        self.assertEqual(JEFF, self.shown(bead).get("assignee"))
        self.assertEqual([f"bench started at {first['start']} on {first['branch']}"] * 2,
                         [c["text"] for c in self.comments(bead)])
        exclude = Path(git(self.repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "info" / "exclude"
        self.assertEqual(1, exclude.read_text(encoding="utf-8").splitlines().count(".worktrees/"))

    def test_ending_posts_the_outcome_on_the_bead_under_the_git_user_name(self):
        bead = self.new_bead("task")

        done = self.bench(self.caller_env(), "end", bead, "landed as 3a9f1c2")

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual([("bench ended: landed as 3a9f1c2", JEFF)],
                         [(c["text"], c["author"]) for c in self.comments(bead)])


class BenchRefusedBeadTests(BenchCase):
    def test_start_refuses_an_epic_and_claims_nothing(self):
        epic = self.new_bead("epic")

        done = self.bench(self.caller_env(), "start", epic)

        self.assertEqual(1, done.returncode)
        self.assertIn("is an epic", done.stderr)
        self.assertEqual("", self.shown(epic).get("assignee", ""))
        self.assertEqual([], self.comments(epic))

    def test_start_refuses_a_bead_someone_else_claimed_and_makes_no_worktree(self):
        bead = self.new_bead("task")
        fixture.run([self.bd, "update", bead, "--assignee", "Someone Else"], self.repo)

        done = self.bench(self.caller_env(), "start", bead)

        self.assertEqual(1, done.returncode)
        self.assertIn("Someone Else", done.stderr)
        self.assertEqual("Someone Else", self.shown(bead).get("assignee"))
        self.assertFalse((self.repo / ".worktrees" / f"print-the-receipt-{self.count}").exists())
        self.assertEqual([], self.comments(bead))

    def test_start_refuses_a_task_whose_epic_the_factory_holds_and_claims_nothing(self):
        epic = self.new_bead("epic")
        fixture.run([self.bd, "label", "add", epic, "factory"], self.repo)
        bead = self.new_task_under(epic)

        done = self.bench(self.caller_env(), "start", bead)

        self.assertEqual(1, done.returncode)
        self.assertIn("factory", done.stderr)
        self.assertEqual("", self.shown(bead).get("assignee", ""))
        self.assertFalse((self.repo / ".worktrees" / f"print-the-receipt-{self.count}").exists())
        self.assertEqual([], self.comments(bead))


class BenchRefusedWorkspaceTests(BenchCase):
    def test_start_refuses_when_the_repo_has_no_git_user_name_and_claims_nothing(self):
        bead = self.new_bead("task")
        git(self.repo, "config", "--unset", "user.name")
        self.addCleanup(git, self.repo, "config", "user.name", JEFF)
        empty_global = self.root / "empty-gitconfig"
        empty_global.write_text("", encoding="utf-8")
        env = {**self.caller_env(), "GIT_CONFIG_GLOBAL": str(empty_global), "GIT_CONFIG_NOSYSTEM": "1"}

        done = self.bench(env, "start", bead)

        self.assertEqual(1, done.returncode)
        self.assertIn("user.name is not set", done.stderr)
        self.assertEqual("", self.shown(bead).get("assignee", ""))

    def test_start_refuses_when_the_worktree_path_is_a_plain_folder_and_leaves_the_bead_unclaimed(self):
        bead = self.new_bead("task")
        blocker = self.repo / ".worktrees" / f"print-the-receipt-{self.count}"
        blocker.mkdir(parents=True)
        (blocker / "notes.txt").write_text("not a worktree\n", encoding="utf-8")

        done = self.bench(self.caller_env(), "start", bead)

        self.assertEqual(1, done.returncode)
        self.assertIn("is not a worktree of the repo", done.stderr)
        shown = self.shown(bead)
        self.assertEqual("open", shown["status"])
        self.assertEqual("", shown.get("assignee", ""))
        self.assertEqual([], self.comments(bead))


class BenchRouteTests(BenchCase):
    def test_route_prints_the_route_this_machine_records_for_the_tier(self):
        light = {"harness": "claude", "model": "haiku", "version": "5.5", "effort": "medium"}
        home = self.root / "home-with-routes"
        home.mkdir(exist_ok=True)
        (home / "settings.json").write_text(json.dumps({"routes": {"light": light}}), encoding="utf-8")

        done = self.bench(self.caller_env(), "route", "light", "--jidoka-home", str(home))

        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(light, json.loads(done.stdout))

    def test_route_refuses_a_tier_the_settings_lack_and_says_to_run_the_installer(self):
        home = self.root / "home-without-deep"
        home.mkdir(exist_ok=True)
        (home / "settings.json").write_text(json.dumps({"routes": {"light": {"harness": "claude"}}}),
                                            encoding="utf-8")

        done = self.bench(self.caller_env(), "route", "deep", "--jidoka-home", str(home))

        self.assertEqual(1, done.returncode)
        self.assertIn("'deep'", done.stderr)
        self.assertIn("install.py", done.stderr)

    def test_route_refuses_a_home_without_settings_and_says_to_run_the_installer(self):
        missing = self.root / "no-such-home"

        done = self.bench(self.caller_env(), "route", "light", "--jidoka-home", str(missing))

        self.assertEqual(1, done.returncode)
        self.assertIn("settings.json does not exist", done.stderr)
        self.assertIn("install.py", done.stderr)


if __name__ == "__main__":
    unittest.main()
