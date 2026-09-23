from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "hermes_agent" / "ingress-prefix-proxy.py"
SPEC = importlib.util.spec_from_file_location("ingress_prefix_proxy", SCRIPT)
assert SPEC and SPEC.loader
ingress_prefix_proxy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingress_prefix_proxy)


class IngressPrefixTest(unittest.TestCase):
    def test_supervisor_ingress_path_becomes_hermes_forwarded_prefix(self) -> None:
        headers = [("X-Ingress-Path", "/api/hassio_ingress/token/"), ("Host", "home.example")]

        self.assertEqual(ingress_prefix_proxy.ingress_prefix(headers), "/api/hassio_ingress/token")

    def test_invalid_ingress_path_is_not_forwarded(self) -> None:
        self.assertIsNone(ingress_prefix_proxy.ingress_prefix([("X-Ingress-Path", "not-a-path")]))

    def test_login_html_root_relative_assets_are_prefixed(self) -> None:
        body = b'<link href="/fonts/ui.woff2"><form action="/auth/password-login">'

        rewritten = ingress_prefix_proxy.rewrite_html(body, "/api/hassio_ingress/token")

        self.assertIn(b'/api/hassio_ingress/token/fonts/ui.woff2', rewritten)
        self.assertIn(b'/api/hassio_ingress/token/auth/password-login', rewritten)
