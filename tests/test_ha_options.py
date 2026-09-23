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



class NativeConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name) / "data"
        self.config = self.home / "config.yaml"
        self.options = self.home / "options.json"
        self.patches = [
            patch.object(ha_options, "HERMES_HOME", self.home),
            patch.object(ha_options, "CONFIG_PATH", self.config),
            patch.object(ha_options, "MAPPED_OPTIONS", self.options),
            patch.object(ha_options, "STANDARD_OPTIONS", Path("/missing/options.json")),
            patch.object(
                ha_options.pwd,
                "getpwnam",
                return_value=types.SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()),
            ),
        ]
        for active_patch in self.patches:
            active_patch.start()
        self.home.mkdir()

    def tearDown(self) -> None:
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temporary.cleanup()

    def test_native_yaml_is_written_atomically_without_translation(self) -> None:
        raw = "model:\n  provider: custom\n  default: native-model\n"

        ha_options.write_native_config(raw)

        self.assertEqual(self.config.read_text(encoding="utf-8"), raw)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o640)

    def test_invalid_or_non_mapping_native_yaml_is_rejected(self) -> None:
        for raw in ("model: [\n", "- not\n- a mapping\n", "null\n"):
            with self.subTest(raw=raw), self.assertRaises(SystemExit):
                ha_options.validate_config(raw)

    def test_startup_mirrors_native_file_instead_of_stale_option(self) -> None:
        native = "model:\n  default: native-wins\n"
        self.config.write_text(native, encoding="utf-8")
        self.options.write_text('{"config_yaml":"model:\\n  default: stale-option\\n"}', encoding="utf-8")

        with patch.object(ha_options, "mirror_native_to_options", return_value=True) as mirror:
            ha_options.startup()

        mirror.assert_called_once_with(native)
        self.assertEqual(self.config.read_text(encoding="utf-8"), native)

    def test_options_path_uses_custom_data_mount(self) -> None:
        self.options.write_text("{}", encoding="utf-8")
        self.assertEqual(ha_options.options_path(), self.options)

    def test_ha_option_edit_writes_native_then_requests_one_restart(self) -> None:
        original = "model:\n  default: native\n"
        edited = "model:\n  default: edited-in-ha\n"
        self.config.write_text(original, encoding="utf-8")
        self.options.write_text('{"config_yaml":"model:\\n  default: native\\n"}', encoding="utf-8")

        def edit_options(_: float) -> None:
            self.options.write_text('{"config_yaml":"model:\\n  default: edited-in-ha\\n"}', encoding="utf-8")

        with patch.object(ha_options, "MIRROR_SETTLE_SECONDS", 0), patch.object(
            ha_options, "request_restart", return_value=True
        ) as restart, patch.object(ha_options.time, "sleep", edit_options):
            ha_options.watch()

        self.assertEqual(self.config.read_text(encoding="utf-8"), edited)
        restart.assert_called_once_with()

    def test_native_edit_mirrors_without_requesting_restart(self) -> None:
        original = "model:\n  default: original\n"
        changed = "model:\n  default: changed-by-hermes\n"
        self.config.write_text(original, encoding="utf-8")
        self.options.write_text('{"config_yaml":"model:\\n  default: original\\n"}', encoding="utf-8")
        calls: list[str] = []

        def change_then_stop(_: float) -> None:
            if not calls:
                calls.append("changed")
                self.config.write_text(changed, encoding="utf-8")
                return
            raise KeyboardInterrupt

        with patch.object(ha_options, "mirror_native_to_options", return_value=True) as mirror, patch.object(
            ha_options, "request_restart"
        ) as restart, patch.object(ha_options.time, "sleep", change_then_stop), self.assertRaises(KeyboardInterrupt):
            ha_options.watch()

        mirror.assert_called_once_with(changed)
        restart.assert_not_called()


class SupervisorApiTest(unittest.TestCase):
    def test_native_mirror_replaces_options_with_only_config_yaml(self) -> None:
        requests: list[tuple[str, dict[str, object]]] = []

        def fake_post(path: str, payload: dict[str, object]) -> bool:
            requests.append((path, payload))
            return True

        with patch.object(ha_options, "supervisor_post", fake_post):
            self.assertTrue(ha_options.mirror_native_to_options("model: {}\n"))

        self.assertEqual(requests, [("/addons/self/options", {"options": {"config_yaml": "model: {}\n"}})])

    def test_config_write_requests_one_supervisor_restart(self) -> None:
        requests: list[tuple[str, dict[str, object]]] = []

        def fake_post(path: str, payload: dict[str, object]) -> bool:
            requests.append((path, payload))
            return True

        with patch.object(ha_options, "supervisor_post", fake_post):
            self.assertTrue(ha_options.request_restart())

        self.assertEqual(requests, [("/addons/self/restart", {})])

