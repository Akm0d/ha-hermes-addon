from __future__ import annotations

import importlib.util
import os
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "hermes_agent" / "ha-options.py"
SPEC = importlib.util.spec_from_file_location("ha_options", SCRIPT)
assert SPEC and SPEC.loader
ha_options = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ha_options)


class HaOptionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name) / "data"
        self.patches = [
            patch.object(ha_options, "HERMES_HOME", self.home),
            patch.object(
                ha_options.pwd,
                "getpwnam",
                return_value=types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()),
            ),
        ]
        for active_patch in self.patches:
            active_patch.start()

    def tearDown(self) -> None:
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temporary.cleanup()

    def test_valid_native_yaml_is_written_atomically_without_translation(self) -> None:
        raw = "model:\n  provider: custom\n  default: my-model\n"

        ha_options.validate_config(raw)
        ha_options.write_config(raw)

        config = self.home / "config.yaml"
        self.assertEqual(config.read_text(encoding="utf-8"), raw)
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o640)

    def test_invalid_or_non_mapping_native_yaml_prevents_startup(self) -> None:
        for raw in ("model: [\n", "- not\n- a mapping\n", "null\n"):
            with self.subTest(raw=raw), self.assertRaises(SystemExit):
                ha_options.validate_config(raw)

    def test_options_path_uses_the_custom_data_mount_when_present(self) -> None:
        options = self.home / "options.json"
        self.home.mkdir()
        options.write_text("{}", encoding="utf-8")
        with patch.object(ha_options, "STANDARD_OPTIONS", Path("/missing/options.json")), patch.object(
            ha_options, "MAPPED_OPTIONS", options
        ):
            self.assertEqual(ha_options.options_path(), options)

class LegacyOptionsTest(unittest.TestCase):
    def test_empty_native_yaml_migrates_verified_legacy_model_settings_once(self) -> None:
        migrated = ha_options.legacy_config_yaml(
            {
                "model_provider": "custom",
                "model_name": "local-model",
                "model_base_url": "http://example/v1",
            },
            "{}\n",
        )

        self.assertEqual(
            ha_options.yaml.safe_load(migrated),
            {
                "model": {
                    "provider": "custom",
                    "default": "local-model",
                    "base_url": "http://example/v1",
                }
            },
        )

    def test_nonempty_native_yaml_wins_over_legacy_model_settings(self) -> None:
        raw = "model:\n  default: user-choice\n"

        self.assertEqual(
            ha_options.legacy_config_yaml({"model_name": "legacy-choice"}, raw),
            raw,
        )

    def test_legacy_options_are_replaced_by_the_single_native_option(self) -> None:
        request_details: dict[str, object] = {}

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

        def fake_urlopen(request, timeout):
            request_details["url"] = request.full_url
            request_details["body"] = request.data
            request_details["authorization"] = request.get_header("Authorization")
            request_details["timeout"] = timeout
            return Response()

        with patch.dict(os.environ, {"SUPERVISOR_TOKEN": "test-token"}, clear=False), patch.object(
            ha_options.urllib.request, "urlopen", fake_urlopen
        ):
            ha_options.remove_legacy_options(
                {"model_name": "legacy-model", "enable_terminal": True},
                "model:\n  default: legacy-model\n",
            )

        self.assertEqual(request_details["url"], "http://supervisor/addons/self/options")
        self.assertEqual(request_details["timeout"], 10)
        self.assertEqual(request_details["authorization"], "Bearer test-token")
        self.assertEqual(
            ha_options.json.loads(request_details["body"]),
            {"options": {"config_yaml": "model:\n  default: legacy-model\n"}},
        )
