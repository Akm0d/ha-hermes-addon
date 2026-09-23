from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.routing import APIWebSocketRoute
import yaml


PLUGIN = Path(__file__).parents[1] / "hermes_agent" / "plugins" / "ha-terminal"
API_PATH = PLUGIN / "dashboard" / "plugin_api.py"
SPEC = importlib.util.spec_from_file_location("ha_terminal_plugin_api", API_PATH)
assert SPEC and SPEC.loader
ha_terminal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ha_terminal)


class HomeAssistantTerminalPluginTest(unittest.TestCase):
    def test_dashboard_manifest_is_a_normal_terminal_tab(self) -> None:
        manifest = json.loads((PLUGIN / "dashboard" / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "ha-terminal")
        self.assertEqual(manifest["label"], "Terminal")
        self.assertEqual(manifest["icon"], "Terminal")
        self.assertEqual(manifest["tab"]["path"], "/ha-terminal")
        self.assertEqual(manifest["api"], "plugin_api.py")

    def test_plugin_api_exposes_only_the_terminal_websocket(self) -> None:
        routes = ha_terminal.router.routes

        self.assertEqual(len(routes), 1)
        self.assertIsInstance(routes[0], APIWebSocketRoute)
        self.assertEqual(routes[0].path, "/terminal")

    def test_frontend_uses_sdk_websocket_url_without_localhost(self) -> None:
        source = (PLUGIN / "dashboard" / "dist" / "index.js").read_text(encoding="utf-8")

        self.assertIn('SDK.buildWsUrl("/api/plugins/ha-terminal/terminal")', source)
        self.assertIn('window.__HERMES_PLUGINS__.register("ha-terminal", TerminalPage)', source)
        self.assertNotIn("localhost", source)
        self.assertNotIn("/app/", source)
        self.assertNotIn("/api/hassio_ingress/", source)

    def test_addon_keeps_terminal_ports_private(self) -> None:
        manifest = yaml.safe_load((Path(__file__).parents[1] / "hermes_agent" / "config.yaml").read_text(encoding="utf-8"))

        self.assertEqual(manifest["ports"], {"8642/tcp": 8642, "9900/tcp": 9900})
        self.assertNotIn("9119/tcp", manifest["ports"])
        self.assertNotIn("9120/tcp", manifest["ports"])

    def test_shell_prefers_bash_and_uses_hermes_home(self) -> None:
        with patch.object(ha_terminal.os, "environ", {"HERMES_HOME": "/tmp/hermes-home"}):
            self.assertEqual(ha_terminal.terminal_home(), Path("/tmp/hermes-home"))
            self.assertEqual(ha_terminal.terminal_argv()[0], "/bin/bash")
            environment = ha_terminal.terminal_environment()

        self.assertEqual(environment["HERMES_HOME"], "/tmp/hermes-home")
        self.assertEqual(environment["HOME"], "/tmp/hermes-home")

    def test_pty_accepts_input_produces_output_resizes_and_reaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge = ha_terminal.PtyBridge.spawn(
                ["/bin/sh", "-i"], cwd=temporary, env={"HOME": temporary, "PATH": os.environ["PATH"], "TERM": "xterm-256color"}
            )
            pid = bridge.pid
            try:
                self.assertTrue(__import__("asyncio").run(bridge.write(b"printf HA_TERMINAL_READY\r")))
                output = b""
                deadline = time.monotonic() + 3
                while b"HA_TERMINAL_READY" not in output and time.monotonic() < deadline:
                    chunk = bridge.read(0.1)
                    if chunk:
                        output += chunk
                self.assertIn(b"HA_TERMINAL_READY", output)
                bridge.resize(cols=120, rows=40)
            finally:
                bridge.close()

            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_terminal_shell_sees_hermes_ha_and_its_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            environment = {
                "HERMES_HOME": temporary,
                "HOME": temporary,
                "PATH": "/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin",
                "TERM": "xterm-256color",
            }
            with patch.object(ha_terminal.os, "environ", environment):
                bridge = ha_terminal.spawn_terminal()
            try:
                command = b"command -v hermes; command -v ha; pwd\r"
                self.assertTrue(__import__("asyncio").run(bridge.write(command)))
                output = b""
                deadline = time.monotonic() + 3
                while temporary.encode() not in output and time.monotonic() < deadline:
                    chunk = bridge.read(0.1)
                    if chunk:
                        output += chunk
                self.assertIn(b"/opt/hermes/.venv/bin/hermes", output)
                self.assertIn(b"/usr/local/bin/ha", output)
                self.assertIn(temporary.encode(), output)
            finally:
                bridge.close()
