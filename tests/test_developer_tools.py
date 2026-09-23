from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
DOCKERFILE = ROOT / "hermes_agent" / "Dockerfile"
INSTALLER = ROOT / "hermes_agent" / "install-ripwire-skills.sh"
MANIFEST = ROOT / "hermes_agent" / "config.yaml"


class DeveloperToolsImageDefinitionTest(unittest.TestCase):
    def test_pins_official_ripwire_and_rtk_release_archives_with_checksums(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("ARG RIPWIRE_VERSION=0.6.2", dockerfile)
        self.assertIn("ARG RTK_VERSION=0.49.0", dockerfile)
        self.assertIn("github.com/redhat-et/ripwire/releases/download/v${RIPWIRE_VERSION}", dockerfile)
        self.assertIn("github.com/rtk-ai/rtk/releases/download/v${RTK_VERSION}", dockerfile)
        self.assertGreaterEqual(dockerfile.count("sha256sum -c -"), 2)
        self.assertIn("amd64)", dockerfile)
        self.assertIn("aarch64)", dockerfile)
        self.assertIn("Unsupported Home Assistant architecture", dockerfile)

    def test_installs_tools_globally_without_changing_hermes_lifecycle(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("/usr/local/bin/ripwire", dockerfile)
        self.assertIn("/usr/local/bin/rtk", dockerfile)
        self.assertIn('CMD ["gateway", "run"]', dockerfile)
        self.assertNotIn("ENTRYPOINT", dockerfile)
        self.assertNotIn("rtk init", dockerfile)
        self.assertNotIn("ripwire mcp", dockerfile.lower())

    def test_skill_installer_preserves_existing_user_skill_directories(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")

        self.assertIn("/opt/hermes/ripwire-skills", installer)
        self.assertIn("${hermes_home}/skills", installer)
        self.assertIn('[ -e "${target_skill}" ] || [ -L "${target_skill}" ]', installer)
        self.assertIn("preserving existing skill", installer)
        self.assertNotIn("rm -rf", installer)

    def test_tooling_adds_no_ports(self) -> None:
        manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(manifest["ports"], {"8642/tcp": 8642, "9900/tcp": 9900})
