from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
ADDON = ROOT / "hermes_agent"


class AddonConfigurationTest(unittest.TestCase):
    def test_manifest_has_no_home_assistant_options_and_preserves_api_ports(self) -> None:
        manifest = yaml.safe_load((ADDON / "config.yaml").read_text(encoding="utf-8"))

        self.assertNotIn("options", manifest)
        self.assertNotIn("schema", manifest)
        self.assertEqual(manifest["ports"], {"8642/tcp": 8642, "9900/tcp": 9900})
        for obsolete_option in ("api_server_key", "hass_url", "hass_token"):
            self.assertNotIn(obsolete_option, manifest)
        self.assertFalse((ADDON / "translations" / "en.yaml").exists())

    def test_wrapper_leaves_api_key_lifecycle_to_persistent_hermes_home(self) -> None:
        dockerfile = (ADDON / "Dockerfile").read_text(encoding="utf-8")
        source_files = "\n".join(path.read_text(encoding="utf-8") for path in ADDON.glob("*.py"))

        self.assertNotIn("ha-environment", dockerfile)
        self.assertNotIn("/addons/self/options", source_files)
        self.assertNotIn("/addons/self/info", source_files)
        self.assertNotIn("SUPERVISOR_TOKEN", source_files)

    def test_documentation_describes_the_internal_openai_endpoint_and_secret_retrieval(self) -> None:
        documentation = "\n".join(
            path.read_text(encoding="utf-8") for path in (ROOT / "README.md", ADDON / "README.md", ADDON / "DOCS.md")
        )

        self.assertIn("http://ab25b854-hermes-agent:8642/v1", documentation)
        self.assertIn("http://<home-assistant-host>:8642/v1", documentation)
        self.assertIn("Model: hermes-agent", documentation)
        self.assertIn("Bearer API_SERVER_KEY", documentation)
        self.assertIn("grep '^API_SERVER_KEY=' /opt/data/.env", documentation)
        self.assertIn("Local OpenAI LLM", documentation)
        self.assertIn("Open WebUI", documentation)

