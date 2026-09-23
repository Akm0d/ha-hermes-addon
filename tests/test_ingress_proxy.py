from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from aiohttp import ClientSession, WSMsgType, web


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

    def test_existing_hermes_base_path_is_not_prefixed_twice(self) -> None:
        prefix = "/api/hassio_ingress/test"
        body = (
            b'<script>window.__HERMES_BASE_PATH__="/api/hassio_ingress/test";</script>'
            b'<script src="/api/hassio_ingress/test/assets/index.js"></script>'
        )

        rewritten = ingress_prefix_proxy.rewrite_html(body, prefix).decode("utf-8")

        self.assertIn('window.__HERMES_BASE_PATH__="/api/hassio_ingress/test"', rewritten)
        self.assertIn('/api/hassio_ingress/test/assets/index.js', rewritten)
        self.assertNotIn('/api/hassio_ingress/test/api/hassio_ingress/test', rewritten)


class IngressAdapterIntegrationTest(unittest.IsolatedAsyncioTestCase):
    prefix = "/api/hassio_ingress/test"

    async def asyncSetUp(self) -> None:
        self.requests: list[tuple[str, list[tuple[bytes, bytes]]]] = []
        self.original_upstream_port = ingress_prefix_proxy.UPSTREAM_PORT

        upstream = web.Application()
        upstream.router.add_route("*", "/{path:.*}", self.upstream)
        self.upstream_runner = web.AppRunner(upstream)
        await self.upstream_runner.setup()
        self.upstream_site = web.TCPSite(self.upstream_runner, "127.0.0.1", 0)
        await self.upstream_site.start()
        ingress_prefix_proxy.UPSTREAM_PORT = self.upstream_site._server.sockets[0].getsockname()[1]

        self.adapter_runner = web.AppRunner(ingress_prefix_proxy.create_app())
        await self.adapter_runner.setup()
        self.adapter_site = web.TCPSite(self.adapter_runner, "127.0.0.1", 0)
        await self.adapter_site.start()
        self.adapter_port = self.adapter_site._server.sockets[0].getsockname()[1]

    async def asyncTearDown(self) -> None:
        await self.adapter_runner.cleanup()
        await self.upstream_runner.cleanup()
        ingress_prefix_proxy.UPSTREAM_PORT = self.original_upstream_port

    @property
    def adapter_url(self) -> str:
        return f"http://127.0.0.1:{self.adapter_port}"

    def ingress_headers(self) -> dict[str, str]:
        return {"X-Ingress-Path": self.prefix + "/"}

    async def upstream(self, request: web.Request) -> web.StreamResponse:
        self.requests.append((request.path, list(request.raw_headers)))
        if request.headers.get("Upgrade", "").lower() == "websocket":
            socket = web.WebSocketResponse()
            await socket.prepare(request)
            await socket.send_str("ready")
            async for message in socket:
                if message.type is WSMsgType.TEXT:
                    await socket.send_str(message.data)
            return socket

        prefix = request.headers.get("X-Forwarded-Prefix", "")
        if request.path in {"/", "/nested/route"}:
            return web.Response(
                content_type="text/html",
                text=(
                    f'<script>window.__HERMES_BASE_PATH__="{prefix}";</script>'
                    f'<script type="module" src="{prefix}/assets/index.js"></script>'
                    f'<link rel="stylesheet" href="{prefix}/assets/index.css">'
                ),
            )
        if request.path == "/api/status":
            return web.json_response({"status": "ok", "base_path": prefix})
        return web.Response(text=request.path)

    def assert_upstream_request(self, path: str) -> None:
        recorded_path, raw_headers = self.requests[-1]
        headers = [(name.lower(), value) for name, value in raw_headers]
        self.assertEqual(recorded_path, path)
        self.assertEqual(headers.count((b"x-forwarded-prefix", self.prefix.encode())), 1)
        self.assertFalse(any(name == b"x-ingress-path" for name, _ in headers))

    async def test_root_html_has_one_prefix_and_prefixed_assets(self) -> None:
        async with ClientSession() as session, session.get(self.adapter_url + "/", headers=self.ingress_headers()) as response:
            html = await response.text()

        self.assertEqual(response.status, 200)
        self.assertIn('window.__HERMES_BASE_PATH__="/api/hassio_ingress/test"', html)
        self.assertIn('/api/hassio_ingress/test/assets/index.js', html)
        self.assertIn('/api/hassio_ingress/test/assets/index.css', html)
        self.assertNotIn('/api/hassio_ingress/test/api/hassio_ingress/test', html)
        self.assert_upstream_request("/")

    async def test_assets_api_and_spa_reload_keep_a_single_prefix(self) -> None:
        async with ClientSession() as session:
            for path in ("/assets/index.js", "/assets/index.css", "/api/status", "/nested/route"):
                async with session.get(self.adapter_url + path, headers=self.ingress_headers()) as response:
                    body = await response.text()
                    self.assertEqual(response.status, 200)
                    if path == "/nested/route":
                        self.assertIn('window.__HERMES_BASE_PATH__="/api/hassio_ingress/test"', body)
                        self.assertNotIn('/api/hassio_ingress/test/api/hassio_ingress/test', body)
                self.assert_upstream_request(path)

    async def test_websocket_uses_logical_path_and_one_forwarded_prefix(self) -> None:
        async with ClientSession() as session:
            async with session.ws_connect(self.adapter_url.replace("http", "ws", 1) + "/api/ws", headers=self.ingress_headers()) as socket:
                message = await socket.receive()

        self.assertEqual(message.type, WSMsgType.TEXT)
        self.assertEqual(message.data, "ready")
        self.assert_upstream_request("/api/ws")
