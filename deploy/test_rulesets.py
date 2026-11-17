"""Validate the importable GitHub ruleset templates and their CI check names.

Standard library only: reads local files and never calls GitHub. Importing and
enforcing the rulesets remains a manual repository-administrator action.
"""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
RULESETS = ROOT / ".github" / "rulesets"
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
GITHUB_ACTIONS_ID = 15368
REQUIRED_CHECKS = (
    "Frontend contracts, build, and isolated mock HTTP",
    "Backend unit and API tests (offline fixtures)",
    "Build and smoke-test containers",
)
POST_PUSH_CHECKS = ("Deploy test", "Deploy production", "Verify public Funnel URL")
# The deploy job renders its check name per environment; match the workflow template.
POST_PUSH_TEMPLATES = ("name: Deploy ${{ needs.build.outputs.target }}", "name: Verify public Funnel URL")


def load(name: str) -> dict:
    return json.loads((RULESETS / name).read_text(encoding="utf-8"))


def rule_types(ruleset: dict) -> list[str]:
    return [rule["type"] for rule in ruleset["rules"]]


def rule(ruleset: dict, rule_type: str) -> dict:
    matches = [item for item in ruleset["rules"] if item["type"] == rule_type]
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one {rule_type} rule, found {len(matches)}")
    return matches[0]


class RulesetStructureTests(unittest.TestCase):
    def test_every_template_is_active_with_explicit_ref_and_bypass(self) -> None:
        for path in sorted(RULESETS.glob("*.json")):
            with self.subTest(ruleset=path.name):
                ruleset = load(path.name)
                self.assertEqual(ruleset["enforcement"], "active")
                self.assertIn(ruleset["target"], {"branch", "tag"})
                self.assertTrue(ruleset["name"].strip())
                self.assertIn("bypass_actors", ruleset)
                includes = ruleset["conditions"]["ref_name"]["include"]
                self.assertTrue(includes)
                self.assertTrue(all(ref.startswith("refs/") for ref in includes))
                self.assertFalse(ruleset["conditions"]["ref_name"]["exclude"])

    def test_templates_are_distinct(self) -> None:
        names = {load(path.name)["name"] for path in RULESETS.glob("*.json")}
        self.assertEqual(len(names), 3)


class MainBranchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ruleset = load("01-main.json")

    def test_targets_only_main(self) -> None:
        self.assertEqual(self.ruleset["target"], "branch")
        self.assertEqual(self.ruleset["conditions"]["ref_name"]["include"], ["refs/heads/main"])

    def test_has_no_bypass_actors(self) -> None:
        self.assertEqual(self.ruleset["bypass_actors"], [])

    def test_blocks_deletion_and_force_push(self) -> None:
        self.assertEqual(set(rule_types(self.ruleset)), {
            "deletion", "non_fast_forward", "pull_request", "required_status_checks"})

    def test_requires_independent_review(self) -> None:
        parameters = rule(self.ruleset, "pull_request")["parameters"]
        self.assertGreaterEqual(parameters["required_approving_review_count"], 1)
        self.assertTrue(parameters["dismiss_stale_reviews_on_push"])
        self.assertTrue(parameters["require_last_push_approval"])
        self.assertTrue(parameters["required_review_thread_resolution"])
        self.assertNotIn("allowed_merge_methods", parameters)

    def test_requires_pre_deployment_checks_from_actions(self) -> None:
        parameters = rule(self.ruleset, "required_status_checks")["parameters"]
        self.assertTrue(parameters["strict_required_status_checks_policy"])
        self.assertFalse(parameters["do_not_enforce_on_create"])
        checks = parameters["required_status_checks"]
        self.assertEqual({check["context"] for check in checks}, set(REQUIRED_CHECKS))
        self.assertTrue(all(check["integration_id"] == GITHUB_ACTIONS_ID for check in checks))


class ReleaseTagTests(unittest.TestCase):
    def test_creation_is_limited_to_repository_admin(self) -> None:
        ruleset = load("02-release-tag-creation.json")
        self.assertEqual(ruleset["target"], "tag")
        self.assertEqual(ruleset["conditions"]["ref_name"]["include"], ["refs/tags/v*"])
        self.assertEqual(rule_types(ruleset), ["creation"])
        self.assertEqual(len(ruleset["bypass_actors"]), 1)
        bypass = ruleset["bypass_actors"][0]
        self.assertEqual(bypass["actor_type"], "RepositoryRole")
        self.assertEqual(bypass["actor_id"], 5)  # GitHub's standard repository admin role.
        self.assertEqual(bypass["bypass_mode"], "always")

    def test_admin_bypass_cannot_reach_immutability(self) -> None:
        creation = load("02-release-tag-creation.json")
        immutability = load("03-release-tag-immutability.json")
        self.assertEqual(immutability["bypass_actors"], [])
        self.assertNotIn("creation", rule_types(immutability))
        self.assertNotEqual(creation["name"], immutability["name"])

    def test_published_tags_cannot_move_or_disappear(self) -> None:
        ruleset = load("03-release-tag-immutability.json")
        self.assertEqual(ruleset["target"], "tag")
        self.assertEqual(ruleset["conditions"]["ref_name"]["include"], ["refs/tags/v*"])
        self.assertEqual(set(rule_types(ruleset)), {"update", "deletion"})
        self.assertFalse(rule(ruleset, "update")["parameters"]["update_allows_fetch_and_merge"])


class WorkflowConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_required_checks_are_real_pull_request_jobs(self) -> None:
        for context in REQUIRED_CHECKS:
            with self.subTest(check=context):
                self.assertIn(f"name: {context}", self.workflow)

    def test_post_push_checks_are_not_required_to_merge(self) -> None:
        required = {check["context"] for check in rule(load("01-main.json"),
                                                       "required_status_checks")["parameters"]["required_status_checks"]}
        for context in POST_PUSH_CHECKS:
            self.assertNotIn(context, required)
        for template in POST_PUSH_TEMPLATES:
            self.assertIn(template, self.workflow)
        for context in REQUIRED_CHECKS:
            self.assertNotIn(context, POST_PUSH_CHECKS)

    def test_tags_deploy_production_from_main(self) -> None:
        self.assertIn('tags: ["v*"]', self.workflow)
        self.assertIn("--is-ancestor", self.workflow)


if __name__ == "__main__":
    unittest.main()
