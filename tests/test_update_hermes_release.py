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
            self.assertIn('version: "5026.9.24-1"', config.read_text(encoding="utf-8"))
            self.assertTrue(
                changelog.read_text(encoding="utf-8").startswith(
                    "# Changelog\n\n## 5026.9.24-1\n\n- Upgraded Hermes container to stable version v2026.9.24.\n"
                )
            )

            second_changed = update_hermes_release.update_release(dockerfile, config, changelog, "v2026.9.24")

            self.assertFalse(second_changed)
            self.assertEqual(changelog.read_text(encoding="utf-8").count("## 5026.9.24-1"), 1)

    def test_accepts_semver_release_after_calendar_version(self) -> None:
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
                "# Changelog\n\n## 2026.9.24-2\n\n- Previous add-on revision.\n",
                encoding="utf-8",
            )

            changed = update_hermes_release.update_release(dockerfile, config, changelog, "v0.22.6")

            self.assertTrue(changed)
            self.assertEqual(dockerfile.read_text(encoding="utf-8").count("v0.22.6"), 2)
            self.assertIn('version: "3000.22.6-1"', config.read_text(encoding="utf-8"))
            self.assertIn("## 3000.22.6-1", changelog.read_text(encoding="utf-8"))
            self.assertFalse(update_hermes_release.update_release(dockerfile, config, changelog, "v0.22.6"))
            self.assertEqual(changelog.read_text(encoding="utf-8").count("## 3000.22.6-1"), 1)

    def test_major_offset_and_future_semver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dockerfile = root / "Dockerfile"
            config = root / "config.yaml"
            changelog = root / "CHANGELOG.md"
            dockerfile.write_text(
                "FROM nousresearch/hermes-agent:v0.22.6 AS hermes_assets\n"
                "FROM nousresearch/hermes-agent:v0.22.6\n",
                encoding="utf-8",
            )
            config.write_text('version: "3000.22.6-2"\n', encoding="utf-8")
            changelog.write_text("# Changelog\n\n## 3000.22.6-2\n\n- Packaging fix.\n", encoding="utf-8")

            self.assertTrue(update_hermes_release.update_release(dockerfile, config, changelog, "v1.0.0"))
            self.assertEqual(dockerfile.read_text(encoding="utf-8").count("v1.0.0"), 2)
            self.assertIn('version: "3001.0.0-1"', config.read_text(encoding="utf-8"))
            self.assertIn("## 3001.0.0-1", changelog.read_text(encoding="utf-8"))
            self.assertFalse(update_hermes_release.update_release(dockerfile, config, changelog, "v1.0.0"))

    def test_single_upstream_from_updates_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dockerfile = root / "Dockerfile"
            config = root / "config.yaml"
            changelog = root / "CHANGELOG.md"
            dockerfile.write_text(
                "FROM nousresearch/hermes-agent:v0.22.6\n",
                encoding="utf-8",
            )
            config.write_text('version: "3000.22.6-2"\n', encoding="utf-8")
            changelog.write_text(
                "# Changelog\n\n## 3000.22.6-2\n\n- Packaging fix.\n",
                encoding="utf-8",
            )
            self.assertTrue(update_hermes_release.update_release(dockerfile, config, changelog, "v0.22.7"))
            self.assertIn("FROM nousresearch/hermes-agent:v0.22.7", dockerfile.read_text())
            self.assertIn('version: "3000.22.7-1"', config.read_text())
            self.assertFalse(update_hermes_release.update_release(dockerfile, config, changelog, "v0.22.7"))

    def test_repository_manifest_matches_upstream_image(self) -> None:
        root = Path(__file__).parents[1]
        dockerfile = (root / "hermes_agent" / "Dockerfile").read_text(encoding="utf-8")
        manifest = (root / "hermes_agent" / "config.yaml").read_text(encoding="utf-8")
        images = update_hermes_release.FROM_PATTERN.findall(dockerfile)
        self.assertEqual(len(images), 1)
        match = update_hermes_release.TAG_PATTERN.fullmatch(images[0][1])
        self.assertIsNotNone(match)
        expected = (
            f'{update_hermes_release.ADDON_MAJOR_OFFSET + int(match.group("major"))}.'
            f'{match.group("minor")}.{match.group("patch")}-1'
        )
        self.assertRegex(manifest, rf'(?m)^version: "{expected}-[1-9][0-9]*"

    def test_rejects_nightly_or_prerelease_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dockerfile = root / "Dockerfile"
            config = root / "config.yaml"
            changelog = root / "CHANGELOG.md"
            for path in (dockerfile, config, changelog):
                path.write_text("# placeholder\n", encoding="utf-8")
            for tag in ("v0.22.6-rc.1", "v0.22.6.dev1", "nightly", "latest"):
                with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "Unsupported Hermes stable tag"):
                    update_hermes_release.update_release(dockerfile, config, changelog, tag)

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
            changelog.write_text("# Changelog\n\n## 5026.9.24-1\n\n- Different entry.\n", encoding="utf-8")

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
)

    def test_rejects_nightly_or_prerelease_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dockerfile = root / "Dockerfile"
            config = root / "config.yaml"
            changelog = root / "CHANGELOG.md"
            for path in (dockerfile, config, changelog):
                path.write_text("# placeholder\n", encoding="utf-8")
            for tag in ("v0.22.6-rc.1", "v0.22.6.dev1", "nightly", "latest"):
                with self.subTest(tag=tag), self.assertRaisesRegex(ValueError, "Unsupported Hermes stable tag"):
                    update_hermes_release.update_release(dockerfile, config, changelog, tag)

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
            changelog.write_text("# Changelog\n\n## 5026.9.24-1\n\n- Different entry.\n", encoding="utf-8")

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
