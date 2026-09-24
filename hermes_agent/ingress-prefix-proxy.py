#!/usr/bin/env python3
"""Translate Supervisor ingress path metadata for Hermes' native dashboard."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Iterable

from aiohttp import ClientSession, WSMsgType, web
from multidict import CIMultiDict


UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = int(os.environ.get("HERMES_DASHBOARD_PORT", "9120"))
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}
PROXY_CONTROL_HEADERS = {"host", "x-ingress-path", "x-forwarded-prefix"}
JAVASCRIPT_CONTENT_TYPES = {"application/javascript", "application/x-javascript", "text/javascript"}
STATIC_RESOURCE_LITERAL = re.compile(
    r"(?P<quote>['\"`])(?P<path>/?(?:assets|fonts)/[^'\"`\\\s]*|/?favicon\.ico)(?P=quote)"
)
TRANSFORMED_RESPONSE_HEADERS = {"content-encoding", "content-length", "content-md5", "etag", "last-modified"}


def ingress_prefix(headers: Iterable[tuple[str, str]]) -> str | None:
    for name, value in headers:
        if name.lower() == "x-ingress-path":
            if value.startswith("/") and not any(character.isspace() for character in value):
                return value.rstrip("/")
            return None
    return None


def upstream_headers(request: web.Request) -> dict[str, str]:
    # Supervisor supplies X-Ingress-Path. Hermes understands X-Forwarded-Prefix,
    # so consume the former rather than forwarding both prefix mechanisms.
    headers = {name: value for name, value in request.headers.items() if name.lower() not in HOP_HEADERS | PROXY_CONTROL_HEADERS}
    if prefix := ingress_prefix(request.headers.items()):
        headers["X-Forwarded-Prefix"] = prefix
    return headers


def upstream_url(request: web.Request) -> str:
    suffix = request.match_info.get("path", "")
    query = f"?{request.query_string}" if request.query_string else ""
    return f"http://{UPSTREAM_HOST}:{UPSTREAM_PORT}/{suffix}{query}"


def rewrite_html(body: bytes, prefix: str | None) -> bytes:
    """Keep login-page root-relative links beneath the Supervisor ingress path."""
    if not prefix:
        return body
    text = body.decode("utf-8")

    def has_prefix(path: str) -> bool:
        return path == prefix or path.startswith(prefix + "/")

    def add_prefix(match: re.Match[str]) -> str:
        quote, path = match.groups()
        return match.group(0) if has_prefix(path) else f"{quote}{prefix}{path}"

    text = re.sub(r"([\"'])(/(?!/)[^\"']*)", add_prefix, text)

    def add_css_prefix(match: re.Match[str]) -> str:
        quote, path = match.groups()
        return match.group(0) if has_prefix(path) else f"url({quote}{prefix}{path}"

    text = re.sub(r"url\((['\"]?)(/(?!/)[^)'\"]*)", add_css_prefix, text)
    return text.encode("utf-8")


def rewrite_javascript(body: bytes, prefix: str | None) -> bytes:
    """Prefix quoted dashboard static-resource URLs, including Vite dependency maps."""
    if not prefix:
        return body
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body

    def add_prefix(match: re.Match[str]) -> str:
        path = match.group("path")
        # Vite/Rolldown dependency maps hold bare paths and prepend their own
        # slash at runtime. Keep those values relative to avoid a
        # protocol-relative //api/... browser URL. Literal root paths, on the
        # other hand, must retain their leading slash.
        rewritten_path = f"{prefix}{path}" if path.startswith("/") else f"{prefix.lstrip('/')}/{path}"
        return f"{match.group('quote')}{rewritten_path}{match.group('quote')}"

    return STATIC_RESOURCE_LITERAL.sub(add_prefix, text).encode("utf-8")


def transformed_response_headers(headers: CIMultiDict[str]) -> CIMultiDict[str]:
    """Discard upstream metadata that describes bytes changed by this adapter."""
    transformed = headers.copy()
    for name in TRANSFORMED_RESPONSE_HEADERS:
        transformed.popall(name, None)
    transformed["Cache-Control"] = "no-store"
    return transformed


async def websocket_proxy(request: web.Request) -> web.WebSocketResponse:
    protocols = [value.strip() for value in request.headers.get("Sec-WebSocket-Protocol", "").split(",") if value.strip()]
    downstream = web.WebSocketResponse(protocols=protocols, autoping=False, autoclose=False)
    await downstream.prepare(request)
    async with ClientSession() as session, session.ws_connect(
        upstream_url(request), headers=upstream_headers(request), protocols=protocols, autoping=False, autoclose=False
    ) as upstream:
        async def forward(source, destination) -> None:
            async for message in source:
                if message.type is WSMsgType.TEXT:
                    await destination.send_str(message.data)
                elif message.type is WSMsgType.BINARY:
                    await destination.send_bytes(message.data)
                elif message.type is WSMsgType.PING:
                    await destination.ping(message.data)
                elif message.type is WSMsgType.PONG:
                    await destination.pong(message.data)
                else:
                    await destination.close()
                    return

        await asyncio.wait(
            [asyncio.create_task(forward(downstream, upstream)), asyncio.create_task(forward(upstream, downstream))],
            return_when=asyncio.FIRST_COMPLETED,
        )
    return downstream


async def proxy(request: web.Request) -> web.StreamResponse:
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await websocket_proxy(request)
    headers = upstream_headers(request)
    # The response may be rewritten below, so do not accept an encoded body.
    headers["Accept-Encoding"] = "identity"
    async with ClientSession() as session, session.request(
        request.method, upstream_url(request), headers=headers, data=request.content.iter_any(), allow_redirects=False
    ) as upstream:
        headers = CIMultiDict((name, value) for name, value in upstream.headers.items() if name.lower() not in HOP_HEADERS)
        if upstream.content_type == "text/html":
            original_body = await upstream.read()
            body = rewrite_html(original_body, ingress_prefix(request.headers.items()))
            if body != original_body:
                headers = transformed_response_headers(headers)
            return web.Response(status=upstream.status, headers=headers, body=body)
        if upstream.content_type in JAVASCRIPT_CONTENT_TYPES:
            original_body = await upstream.read()
            body = rewrite_javascript(original_body, ingress_prefix(request.headers.items()))
            if body != original_body:
                headers = transformed_response_headers(headers)
            return web.Response(status=upstream.status, headers=headers, body=body)
        response = web.StreamResponse(status=upstream.status, headers=headers)
        await response.prepare(request)
        async for chunk in upstream.content.iter_any():
            await response.write(chunk)
        await response.write_eof()
        return response


def create_app() -> web.Application:
    application = web.Application()
    application.router.add_route("*", "/{path:.*}", proxy)
    return application


app = create_app()

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=9119, print=None)
