from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / ".github" / "scripts" / "update_hermes_release.py"
WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "update-hermes.yml"
SPEC = importlib.util.spec_from_file_location("update_hermes_release", SCRIPT)
assert SPEC and SPEC.loader
update_hermes_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_hermes_release)


class HermesReleaseUpdaterTest(unittest.TestCase):
    def test_workflow_uses_the_guarded_transform_and_commits_the_changelog(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn('python3 .github/scripts/update_hermes_release.py "${TAG}"', workflow)
        self.assertIn("hermes_agent/CHANGELOG.md", workflow)
        self.assertIn("git diff --check", workflow)

    def test_updates_all_release_files_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dockerfile = root / "Dockerfile"
            config = root / "config.yaml"
            changelog = root / "CHANGELOG.md"
            dockerfile.write_text(
                "FROM nousresearch/hermes-agent:v2026.9.21 AS hermes_assets\n"
                "FROM nousresearch/hermes-agent:v2026.9.21\n",
                encoding="utf-8",
            )
            config.write_text('name: Hermes Agent\nversion: "2026.9.21-15"\n', encoding="utf-8")
            changelog.write_text("# Changelog\n\n## 2026.9.21-15\n\n- Previous release.\n", encoding="utf-8")
            dockerfile.chmod(0o644)

            changed = update_hermes_release.update_release(dockerfile, config, changelog, "v2026.9.24")

            self.assertTrue(changed)
            self.assertEqual(dockerfile.read_text(encoding="utf-8").count("v2026.9.24"), 2)
            self.assertEqual(dockerfile.stat().st_mode & 0o777, 0o644)
            self.assertIn('version: "2026.9.24-1"', config.read_text(encoding="utf-8"))
            self.assertTrue(
                changelog.read_text(encoding="utf-8").startswith(
                    "# Changelog\n\n## 2026.9.24-1\n\n- Upgraded Hermes container to stable version v2026.9.24.\n"
                )
            )

            second_changed = update_hermes_release.update_release(dockerfile, config, changelog, "v2026.9.24")

            self.assertFalse(second_changed)
            self.assertEqual(changelog.read_text(encoding="utf-8").count("## 2026.9.24-1"), 1)

    def test_rejects_duplicate_or_malformed_changelog_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dockerfile = root / "Dockerfile"
            config = root / "config.yaml"
            changelog = root / "CHANGELOG.md"
            dockerfile.write_text(
                "FROM nousresearch/hermes-agent:v2026.9.21 AS hermes_assets\n"
                "FROM nousresearch/hermes-agent:v2026.9.21\n",
                encoding="utf-8",
            )
            config.write_text('version: "2026.9.21-15"\n', encoding="utf-8")
            changelog.write_text("# Changelog\n\n## 2026.9.24-1\n\n- Different entry.\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "does not contain"):
                update_hermes_release.update_release(dockerfile, config, changelog, "v2026.9.24")

    def test_same_upstream_tag_does_not_downgrade_a_manual_addon_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dockerfile = root / "Dockerfile"
            config = root / "config.yaml"
            changelog = root / "CHANGELOG.md"
            dockerfile.write_text(
                "FROM nousresearch/hermes-agent:v2026.9.24 AS hermes_assets\n"
                "FROM nousresearch/hermes-agent:v2026.9.24\n",
                encoding="utf-8",
            )
            config.write_text('version: "2026.9.24-2"\n', encoding="utf-8")
            changelog.write_text(
                "# Changelog\n\n## 2026.9.24-2\n\n- Add-on-only fix.\n\n"
                "## 2026.9.24-1\n\n- Upgraded Hermes container to stable version v2026.9.24.\n",
                encoding="utf-8",
            )

            changed = update_hermes_release.update_release(dockerfile, config, changelog, "v2026.9.24")

            self.assertFalse(changed)
            self.assertIn('version: "2026.9.24-2"', config.read_text(encoding="utf-8"))
            self.assertEqual(changelog.read_text(encoding="utf-8").count("## 2026.9.24-1"), 1)
