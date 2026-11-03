from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
DOCKERFILE = ROOT / "hermes_agent" / "Dockerfile"
WORKFLOW = ROOT / ".github" / "workflows" / "update-hermes.yml"
PLUGIN = ROOT / "hermes_agent" / "plugins" / "ha-terminal" / "dashboard" / "dist" / "index.js"


class TerminalAssetPipelineTest(unittest.TestCase):
    def test_terminal_assets_are_independent_of_upstream_hermes_internals(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("AS terminal_assets", dockerfile)
        self.assertIn("@xterm/xterm@6.0.0", dockerfile)
        self.assertIn("@xterm/addon-fit@0.11.0", dockerfile)
        self.assertEqual(dockerfile.count("COPY --from=terminal_assets"), 3)
        self.assertNotIn("COPY --from=hermes_assets", dockerfile)
        self.assertNotIn("/opt/hermes/node_modules/@xterm/", dockerfile)

    def test_terminal_runtime_paths_match_bundled_asset_names(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        index = PLUGIN.read_text(encoding="utf-8")
        for name in ("xterm.js", "xterm-fit.js", "xterm.css"):
            self.assertIn(f"/opt/hermes/plugins/ha-terminal/dashboard/dist/{name}", dockerfile)
        self.assertIn('loadScript("xterm.js", "Terminal")', index)
        self.assertIn('loadScript("xterm-fit.js", "FitAddon")', index)

    def test_release_workflow_builds_updated_addon_before_push(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Build Home Assistant image before publishing release", workflow)
        self.assertIn("--file hermes_agent/Dockerfile", workflow)
        self.assertIn("--build-arg BUILD_ARCH=amd64", workflow)
        self.assertLess(
            workflow.index("Build Home Assistant image before publishing release"),
            workflow.index("- name: Commit and push"),
        )

    def test_packaging_bump_is_not_an_upstream_image_change(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        manifest = (ROOT / "hermes_agent" / "config.yaml").read_text(encoding="utf-8")
        self.assertEqual(
            re.findall(r"^FROM nousresearch/hermes-agent:(\S+)", dockerfile, re.MULTILINE),
            ["v0.22.6"],
        )
        self.assertIn('version: "3000.22.6-2"', manifest)
