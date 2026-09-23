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
        self.real_ha = Path(self.temporary.name) / "ha"
        self.real_ha.write_text("#!/bin/sh\n", encoding="utf-8")
        self.real_ha.chmod(0o755)
        self.patches = [
            patch.object(ha_options, "HERMES_HOME", self.home),
            patch.object(ha_options, "REAL_HA", self.real_ha),
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

    def test_cli_gate_removes_execute_access_when_disabled_and_restores_it_when_enabled(self) -> None:
        ha_options.apply_ha_cli_gate(False)
        self.assertEqual(stat.S_IMODE(self.real_ha.stat().st_mode), 0o700)

        ha_options.apply_ha_cli_gate(True)
        self.assertEqual(stat.S_IMODE(self.real_ha.stat().st_mode), 0o755)
