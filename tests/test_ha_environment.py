from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import yaml


SCRIPT = Path(__file__).parents[1] / "hermes_agent" / "ha-environment.py"
ADDON_CONFIG = Path(__file__).parents[1] / "hermes_agent" / "config.yaml"
SPEC = importlib.util.spec_from_file_location("ha_environment", SCRIPT)
assert SPEC and SPEC.loader
ha_environment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ha_environment)


class HomeAssistantEnvironmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.environment = self.root / "environment"
        self.s6_patch = patch.object(ha_environment, "S6_ENVIRONMENT", self.environment)
        self.s6_patch.start()

    def tearDown(self) -> None:
        self.s6_patch.stop()
        self.temporary.cleanup()

    def test_existing_key_is_reused_and_injected_without_mutation(self) -> None:
        request = unittest.mock.Mock(return_value={"result": "ok", "data": {"options": {"api_server_key": "existing-key"}}})

        with patch.object(ha_environment, "supervisor_request", request):
            ha_environment.configure_environment()

        self.assertEqual((self.environment / "API_SERVER_KEY").read_text(), "existing-key")
        self.assertEqual(sorted(item.name for item in self.environment.iterdir()), ["API_SERVER_KEY"])
        request.assert_called_once_with("GET", "/addons/self/info")

    def test_supervisor_requests_use_authenticated_self_endpoints_and_result_data_envelope(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b'{"result":"ok","data":{"options":{"api_server_key":"api-key"}}}'

        opener = unittest.mock.Mock(return_value=Response())
        with patch.dict(ha_environment.os.environ, {"SUPERVISOR_TOKEN": "supervisor-token"}, clear=True), patch.object(
            ha_environment, "urlopen", opener
        ):
            self.assertEqual(ha_environment.load_options(), {"api_server_key": "api-key"})

        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "http://supervisor/addons/self/info")
        self.assertEqual(request.get_header("Authorization"), "Bearer supervisor-token")

    def test_empty_key_generates_secure_key_and_persists_only_supported_option(self) -> None:
        request = unittest.mock.Mock(side_effect=[
            {"result": "ok", "data": {"options": {"hass_url": "old", "hass_token": "old", "api_server_key": ""}}},
            {"result": "ok", "data": {}},
        ])

        output = io.StringIO()
        with patch.object(ha_environment, "supervisor_request", request), patch.object(
            ha_environment.secrets, "token_urlsafe", return_value="generated-secure-key"
        ), contextlib.redirect_stdout(output):
            ha_environment.configure_environment()

        self.assertEqual((self.environment / "API_SERVER_KEY").read_text(), "generated-secure-key")
        self.assertEqual(
            request.call_args_list,
            [
                unittest.mock.call("GET", "/addons/self/info"),
                unittest.mock.call("POST", "/addons/self/options", {"options": {"api_server_key": "generated-secure-key"}}),
            ],
        )
        self.assertNotIn("generated-secure-key", output.getvalue())

    def test_subsequent_startup_reuses_persisted_generated_key(self) -> None:
        persisted = {"api_server_key": "generated-secure-key"}
        request = unittest.mock.Mock(return_value={"result": "ok", "data": {"options": persisted}})

        with patch.object(ha_environment, "supervisor_request", request):
            ha_environment.configure_environment()
            ha_environment.configure_environment()

        self.assertEqual((self.environment / "API_SERVER_KEY").read_text(), "generated-secure-key")
        self.assertEqual(request.call_count, 2)
        self.assertTrue(all(call.args == ("GET", "/addons/self/info") for call in request.call_args_list))

    def test_existing_key_survives_obsolete_option_cleanup_failure(self) -> None:
        request = unittest.mock.Mock(side_effect=[
            {"result": "ok", "data": {"options": {"api_server_key": "existing-key", "hass_url": "obsolete"}}},
            SystemExit(1),
        ])

        with patch.object(ha_environment, "supervisor_request", request):
            ha_environment.configure_environment()

        self.assertEqual((self.environment / "API_SERVER_KEY").read_text(), "existing-key")

    def test_native_hermes_files_are_untouched(self) -> None:
        hermes_home = self.root / "hermes-home"
        hermes_home.mkdir()
        config = hermes_home / "config.yaml"
        dotenv = hermes_home / ".env"
        config.write_text("model: native\n", encoding="utf-8")
        dotenv.write_text("HASS_TOKEN=native-token\nHASS_URL=http://native\n", encoding="utf-8")
        request = unittest.mock.Mock(return_value={"result": "ok", "data": {"options": {"api_server_key": "api-key"}}})

        with patch.object(ha_environment, "supervisor_request", request):
            ha_environment.configure_environment()

        self.assertEqual(config.read_text(encoding="utf-8"), "model: native\n")
        self.assertEqual(dotenv.read_text(encoding="utf-8"), "HASS_TOKEN=native-token\nHASS_URL=http://native\n")

    def test_supervisor_failure_does_not_leak_its_token(self) -> None:
        secret = "supervisor-token-must-not-appear"
        output = io.StringIO()

        with patch.dict(ha_environment.os.environ, {"SUPERVISOR_TOKEN": secret}, clear=True), patch.object(
            ha_environment, "urlopen", side_effect=URLError(secret)
        ), contextlib.redirect_stderr(output), self.assertRaises(SystemExit):
            ha_environment.load_options()

        self.assertNotIn(secret, output.getvalue())
        self.assertIn("Supervisor app-options request failed", output.getvalue())

    def test_manifest_exposes_only_api_key_and_preserves_existing_ports(self) -> None:
        manifest = yaml.safe_load(ADDON_CONFIG.read_text(encoding="utf-8"))
        translations = yaml.safe_load((ADDON_CONFIG.parent / "translations" / "en.yaml").read_text(encoding="utf-8"))
        source = SCRIPT.read_text(encoding="utf-8")

        self.assertEqual(manifest["options"], {"api_server_key": ""})
        self.assertEqual(manifest["schema"], {"api_server_key": "password"})
        self.assertEqual(set(translations["configuration"]), {"api_server_key"})
        self.assertEqual(manifest["ports"], {"8642/tcp": 8642, "9900/tcp": 9900})
        self.assertNotIn("hass_url", manifest["options"])
        self.assertNotIn("hass_token", manifest["options"])
        self.assertNotIn("a2a_bearer_token", manifest["options"])
        self.assertNotIn("options.json", source)
        self.assertNotIn('"HASS_URL"', source)
        self.assertNotIn('"HASS_TOKEN"', source)
