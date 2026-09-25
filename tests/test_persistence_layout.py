from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
ADDON = ROOT / "hermes_agent"


class PersistenceLayoutTest(unittest.TestCase):
    def test_user_plugins_use_persistent_hermes_home_not_image_plugin_tree(self) -> None:
        documentation = (ADDON / "DOCS.md").read_text(encoding="utf-8")
        dockerfile = (ADDON / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("/opt/data/plugins/", documentation)
        self.assertIn("/opt/hermes/plugins/", documentation)
        self.assertIn("COPY plugins/ha-terminal /opt/hermes/plugins/ha-terminal", dockerfile)
        self.assertNotIn("/opt/hermes/plugins -> /opt/data/plugins", documentation)

    def test_doctor_compatibility_link_is_narrow_and_preserves_user_files(self) -> None:
        hook = (ADDON / "025-hermes-command-link").read_text(encoding="utf-8")

        self.assertIn("/opt/hermes/.venv/bin/hermes", hook)
        self.assertIn("Leaving user-managed Hermes command", hook)
        self.assertIn("/opt/hermes/.venv/bin/hermes|/opt/hermes/venv/bin/hermes", hook)
        self.assertNotIn("rm -rf", hook)
        self.assertNotIn("/opt/hermes/plugins", hook)
