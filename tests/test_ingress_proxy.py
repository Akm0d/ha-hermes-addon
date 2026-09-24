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

    def test_javascript_static_literals_and_vite_dependency_maps_use_the_ingress_prefix_once(self) -> None:
        prefix = "/api/hassio_ingress/test"
        source = (
            b'const deps = ['
            b'"assets/ConfigPage-DaxHB67Y.js",'
            b'"assets/rolldown-runtime-CbXtAM7H.js",'
            b'"assets/react-vendor-BoVnYuL4.js"'
            b'];'
            b'const bare_double = "assets/foo.js";'
            b"const bare_single = 'assets/foo.js';"
            b"const bare_template = `assets/foo.js`;"
            b'import("/assets/usePageHeader-BtGwRGnc.js");'
            b"import('/assets/theme.css');"
            b"const wasm = `/assets/dashboard.wasm`;"
            b'const font = "fonts/ui.woff2";'
            b'const favicon = "favicon.ico";'
            b'const root_font = "/fonts/ui.woff2";'
            b'const root_favicon = "/favicon.ico";'
            b'const card = "/api/hassio_ingress/test/assets/already.js";'
            b'const local = "./foo.js";'
            b'const parent = "../foo.js";'
            b'const remote = "https://example.test/assets/remote.js";'
            b'const api = "/api/status";'
            b'const relative_api = "api/status";'
        )

        rewritten = ingress_prefix_proxy.rewrite_javascript(source, prefix).decode("utf-8")

        self.assertIn(
            'const deps = ["api/hassio_ingress/test/assets/ConfigPage-DaxHB67Y.js",'
            '"api/hassio_ingress/test/assets/rolldown-runtime-CbXtAM7H.js",'
            '"api/hassio_ingress/test/assets/react-vendor-BoVnYuL4.js"];',
            rewritten,
        )
        self.assertIn('"api/hassio_ingress/test/assets/foo.js"', rewritten)
        self.assertIn("'api/hassio_ingress/test/assets/foo.js'", rewritten)
        self.assertIn("`api/hassio_ingress/test/assets/foo.js`", rewritten)
        self.assertIn('import("/api/hassio_ingress/test/assets/usePageHeader-BtGwRGnc.js")', rewritten)
        self.assertIn("import('/api/hassio_ingress/test/assets/theme.css')", rewritten)
        self.assertIn("`/api/hassio_ingress/test/assets/dashboard.wasm`", rewritten)
        self.assertIn('"api/hassio_ingress/test/fonts/ui.woff2"', rewritten)
        self.assertIn('"api/hassio_ingress/test/favicon.ico"', rewritten)
        self.assertIn('"/api/hassio_ingress/test/fonts/ui.woff2"', rewritten)
        self.assertIn('"/api/hassio_ingress/test/favicon.ico"', rewritten)
        self.assertIn('"/api/hassio_ingress/test/assets/already.js"', rewritten)
        self.assertIn('"./foo.js"', rewritten)
        self.assertIn('"../foo.js"', rewritten)
        self.assertIn('"https://example.test/assets/remote.js"', rewritten)
        self.assertIn('"/api/status"', rewritten)
        self.assertIn('"api/status"', rewritten)
        self.assertNotIn('"assets/ConfigPage-DaxHB67Y.js"', rewritten)
        self.assertNotIn('"assets/rolldown-runtime-CbXtAM7H.js"', rewritten)
        self.assertNotIn('"/assets/usePageHeader-BtGwRGnc.js"', rewritten)
        self.assertNotIn('"/api/hassio_ingress/test/assets/ConfigPage-DaxHB67Y.js"', rewritten)
        self.assertNotIn('//api/hassio_ingress/', rewritten)
        self.assertNotIn('/api/hassio_ingress/test/api/hassio_ingress/test', rewritten)


class IngressAdapterIntegrationTest(unittest.IsolatedAsyncioTestCase):
    prefix = "/api/hassio_ingress/test"

    async def asyncSetUp(self) -> None:
        self.requests: list[tuple[str, list[tuple[bytes, bytes]]]] = []
        self.request_queries: list[str] = []
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

    def websocket_ingress_headers(self) -> dict[str, str]:
        return {
            **self.ingress_headers(),
            "Origin": "https://hearth.example",
            "X-Forwarded-For": "203.0.113.10",
            "X-Forwarded-Host": "hearth.example",
            "X-Forwarded-Proto": "https",
            "X-Real-IP": "203.0.113.10",
        }

    async def upstream(self, request: web.Request) -> web.StreamResponse:
        self.requests.append((request.path, list(request.raw_headers)))
        self.request_queries.append(request.query_string)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            if request.headers.get("Origin") or request.headers.get("Host") != f"127.0.0.1:{ingress_prefix_proxy.UPSTREAM_PORT}":
                return web.Response(status=403, text="origin_mismatch")
            socket = web.WebSocketResponse()
            await socket.prepare(request)
            await socket.send_str("ready")
            async for message in socket:
                if message.type is WSMsgType.TEXT:
                    await socket.send_str(message.data)
                elif message.type is WSMsgType.BINARY:
                    await socket.send_bytes(message.data)
            return socket

        prefix = request.headers.get("X-Forwarded-Prefix", "")
        if request.path in {"/", "/nested/route"}:
            return web.Response(
                content_type="text/html",
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "ETag": '"upstream-html"',
                    "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT",
                    "Content-MD5": "upstream-html-md5",
                    "Content-Encoding": "identity",
                },
                text=(
                    f'<script>window.__HERMES_BASE_PATH__="{prefix}";</script>'
                    f'<script type="module" src="{prefix}/assets/index.js"></script>'
                    f'<link rel="stylesheet" href="{prefix}/assets/index.css">'
                    '<link rel="preload" href="/fonts/ui.woff2">'
                ),
            )
        if request.path == "/api/status":
            return web.json_response({"status": "ok", "base_path": prefix})
        if request.path == "/assets/lazy.js":
            return web.Response(
                content_type="application/javascript",
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "ETag": '"upstream-javascript"',
                    "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT",
                    "Content-MD5": "upstream-javascript-md5",
                    "Content-Encoding": "identity",
                },
                text=(
                    'const deps = ["assets/ConfigPage-DaxHB67Y.js", '
                    '"assets/rolldown-runtime-CbXtAM7H.js", '
                    '"assets/react-vendor-BoVnYuL4.js"]; '
                    'import("/assets/usePageHeader-BtGwRGnc.js"); const api = "/api/status";'
                ),
            )
        if request.path == "/assets/untouched.js":
            return web.Response(
                content_type="application/javascript",
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "ETag": '"upstream-untouched"',
                    "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT",
                    "Content-MD5": "upstream-untouched-md5",
                    "Content-Encoding": "identity",
                },
                text='const api = "/api/status";',
            )
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
        self.assertIn('/api/hassio_ingress/test/fonts/ui.woff2', html)
        self.assertNotIn('/api/hassio_ingress/test/api/hassio_ingress/test', html)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn("ETag", response.headers)
        self.assertNotIn("Last-Modified", response.headers)
        self.assertNotIn("Content-MD5", response.headers)
        self.assertNotIn("Content-Encoding", response.headers)
        self.assertEqual(int(response.headers["Content-Length"]), len(html.encode("utf-8")))
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

    async def test_lazy_javascript_assets_keep_the_dynamic_ingress_prefix(self) -> None:
        async with ClientSession() as session:
            async with session.get(self.adapter_url + "/assets/lazy.js", headers=self.ingress_headers()) as response:
                body = await response.text()

        self.assertEqual(response.status, 200)
        self.assertEqual(response.content_type, "application/javascript")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertNotIn("ETag", response.headers)
        self.assertNotIn("Last-Modified", response.headers)
        self.assertNotIn("Content-MD5", response.headers)
        self.assertNotIn("Content-Encoding", response.headers)
        self.assertEqual(int(response.headers["Content-Length"]), len(body.encode("utf-8")))
        self.assertIn('"api/hassio_ingress/test/assets/ConfigPage-DaxHB67Y.js"', body)
        self.assertIn('"api/hassio_ingress/test/assets/rolldown-runtime-CbXtAM7H.js"', body)
        self.assertIn('"api/hassio_ingress/test/assets/react-vendor-BoVnYuL4.js"', body)
        self.assertIn('import("/api/hassio_ingress/test/assets/usePageHeader-BtGwRGnc.js")', body)
        self.assertIn('"/api/status"', body)
        self.assertNotIn('"assets/ConfigPage-DaxHB67Y.js"', body)
        self.assertNotIn('"assets/rolldown-runtime-CbXtAM7H.js"', body)
        self.assertNotIn('"/assets/usePageHeader-BtGwRGnc.js"', body)
        self.assertNotIn('"/api/hassio_ingress/test/assets/ConfigPage-DaxHB67Y.js"', body)
        self.assertNotIn('//api/hassio_ingress/', body)
        self.assert_upstream_request("/assets/lazy.js")
        headers = {name.lower(): value for name, value in self.requests[-1][1]}
        self.assertEqual(headers[b"accept-encoding"], b"identity")

    async def test_untouched_javascript_keeps_upstream_cache_headers(self) -> None:
        async with ClientSession() as session:
            async with session.get(self.adapter_url + "/assets/untouched.js", headers=self.ingress_headers()) as response:
                body = await response.text()

        self.assertEqual(response.status, 200)
        self.assertEqual(body, 'const api = "/api/status";')
        self.assertEqual(response.headers["Cache-Control"], "public, max-age=31536000, immutable")
        self.assertEqual(response.headers["ETag"], '"upstream-untouched"')
        self.assertEqual(response.headers["Last-Modified"], "Wed, 21 Oct 2015 07:28:00 GMT")
        self.assertEqual(response.headers["Content-MD5"], "upstream-untouched-md5")
        self.assertEqual(response.headers["Content-Encoding"], "identity")
        self.assertEqual(int(response.headers["Content-Length"]), len(body.encode("utf-8")))
        self.assert_upstream_request("/assets/untouched.js")

    async def test_websocket_uses_logical_path_and_one_forwarded_prefix(self) -> None:
        paths = ("/api/pty", "/api/events", "/api/ws", "/api/pub", "/api/console")
        async with ClientSession() as session:
            for path in paths:
                async with session.ws_connect(
                    self.adapter_url.replace("http", "ws", 1) + path + "?ticket=dashboard-token&channel=chat",
                    headers=self.websocket_ingress_headers(),
                ) as socket:
                    message = await socket.receive()
                    self.assertEqual(message.type, WSMsgType.TEXT)
                    self.assertEqual(message.data, "ready")
                    await socket.send_str("prompt")
                    message = await socket.receive()
                    self.assertEqual(message.type, WSMsgType.TEXT)
                    self.assertEqual(message.data, "prompt")
                    await socket.send_bytes(b"resize")
                    message = await socket.receive()
                    self.assertEqual(message.type, WSMsgType.BINARY)
                    self.assertEqual(message.data, b"resize")

                self.assert_upstream_request(path)
                self.assertEqual(self.request_queries[-1], "ticket=dashboard-token&channel=chat")
                headers = {name.lower(): value for name, value in self.requests[-1][1]}
                self.assertEqual(headers[b"host"], f"127.0.0.1:{ingress_prefix_proxy.UPSTREAM_PORT}".encode())
                self.assertNotIn(b"origin", headers)
                self.assertNotIn(b"forwarded", headers)
                self.assertNotIn(b"x-forwarded-for", headers)
                self.assertNotIn(b"x-forwarded-host", headers)
                self.assertNotIn(b"x-forwarded-proto", headers)
                self.assertNotIn(b"x-real-ip", headers)
