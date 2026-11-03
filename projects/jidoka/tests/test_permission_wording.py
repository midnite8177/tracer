import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jidoka_fixture as fixture  # noqa: E402

sys.path.insert(0, str(fixture.PROJECT / "plugin" / "jidoka" / "scripts"))

import permission_question as pq  # noqa: E402

LINT = pq.Denial("cd packages/till && make lint --fix", "make lint")
REMOVE = pq.Denial("rm -rf ../shared/cache build", "rm")


class PermissionWordingCase(unittest.TestCase):
    """The permission question's wording and answer reading as plain functions, with no repo and no bd."""

    def test_a_delete_outside_the_worktree_names_the_paths_it_tried_to_delete(self):
        self.assertEqual("The worker tried to delete ../shared/cache build with rm. "
                         "Workers may delete only inside their worktree, so the task stopped.",
                         pq.situation_on_page(pq.Denied(REMOVE, pq.OUTSIDE_WORKTREE)))

    def test_the_diagram_shows_the_task_the_call_the_denial_and_the_park(self):
        steps = pq.steps_on_page("shop-1", pq.Denied(LINT, pq.OFF_LISTS))
        self.assertEqual(["The worker was building shop-1",
                          "It made the call cd packages/till && make lint --fix",
                          "The call was denied, because workers may not run make lint",
                          "The task is parked and waits for your answer"], list(steps))

    def test_only_the_option_given_a_reason_shows_the_workers_pick(self):
        picked = pq.permission_option("epic", 50, LINT, "the lint step is part of the build")
        other = pq.permission_option("repo", 30, LINT, None)
        self.assertIn("The worker picks it because: the lint step is part of the build", picked.line())
        self.assertNotIn("The worker picks it", other.line())
        self.assertIn("Answer word: repo.", other.line())

    def test_a_list_name_that_continues_into_a_longer_word_names_no_list(self):
        self.assertEqual("none", pq.list_named(("epic-sized change, no",)))


if __name__ == "__main__":
    unittest.main()
