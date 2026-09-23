from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "hermes_agent" / "ha-environment.py"
SPEC = importlib.util.spec_from_file_location("ha_environment", SCRIPT)
assert SPEC and SPEC.loader
ha_environment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ha_environment)


class HomeAssistantEnvironmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.options = root / "options.json"
        self.environment = root / "environment"
        self.patches = [
            patch.object(ha_environment, "STANDARD_OPTIONS", self.options),
            patch.object(ha_environment, "MAPPED_OPTIONS", root / "missing-options.json"),
            patch.object(ha_environment, "S6_ENVIRONMENT", self.environment),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self) -> None:
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temporary.cleanup()

    def test_materializes_only_the_three_integration_values(self) -> None:
        self.options.write_text(
            '{"hass_url":"http://homeassistant.local:8123/","hass_token":"long-lived-token","api_server_key":"api-key"}',
            encoding="utf-8",
        )

        ha_environment.configure_environment(ha_environment.load_options())

        self.assertEqual((self.environment / "HASS_URL").read_text(), "http://homeassistant.local:8123")
        self.assertEqual((self.environment / "HASS_TOKEN").read_text(), "long-lived-token")
        self.assertEqual((self.environment / "API_SERVER_KEY").read_text(), "api-key")
        self.assertEqual(sorted(item.name for item in self.environment.iterdir()), ["API_SERVER_KEY", "HASS_TOKEN", "HASS_URL"])

    def test_blank_hass_values_are_not_persisted_as_runtime_environment(self) -> None:
        self.options.write_text('{"hass_url":"","hass_token":"","api_server_key":"api-key"}', encoding="utf-8")
        self.environment.mkdir()
        (self.environment / "HASS_URL").write_text("stale", encoding="utf-8")
        (self.environment / "HASS_TOKEN").write_text("stale", encoding="utf-8")

        ha_environment.configure_environment(ha_environment.load_options())

        self.assertFalse((self.environment / "HASS_URL").exists())
        self.assertFalse((self.environment / "HASS_TOKEN").exists())
        self.assertEqual((self.environment / "API_SERVER_KEY").read_text(), "api-key")

    def test_blank_api_key_prevents_startup(self) -> None:
        with self.assertRaisesRegex(SystemExit, "1"):
            ha_environment.configure_environment({"api_server_key": "   "})

    def test_hass_url_must_be_a_base_url(self) -> None:
        for value in ("homeassistant.local:8123", "http://homeassistant.local:8123/api", "http://host/?query=1"):
            with self.subTest(value=value), self.assertRaisesRegex(SystemExit, "1"):
                ha_environment.configure_environment({"hass_url": value, "api_server_key": "api-key"})
