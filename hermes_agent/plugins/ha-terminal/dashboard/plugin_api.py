"""PTY-backed dashboard terminal for the Home Assistant Hermes container."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from hermes_cli.pty_bridge import PtyBridge, PtyUnavailableError
from hermes_cli.web_server_chat import _ws_auth_ok


router = APIRouter()
log = logging.getLogger("ha_terminal")
_MAX_INPUT_BYTES = 64 * 1024


def terminal_home() -> Path:
    """Return the dashboard process' Hermes home without touching config."""
    return Path(os.environ.get("HERMES_HOME", "/opt/data"))


def terminal_argv() -> list[str]:
    """Use the image shell, preferring bash for full interactive compatibility."""
    return ["/bin/bash", "-i"] if Path("/bin/bash").is_file() else ["/bin/sh", "-i"]


def terminal_environment() -> dict[str, str]:
    """Preserve the dashboard process environment for the child shell only."""
    environment = os.environ.copy()
    environment.setdefault("HOME", str(terminal_home()))
    environment.setdefault("HERMES_HOME", str(terminal_home()))
    environment.setdefault("TERM", "xterm-256color")
    return environment


def spawn_terminal(cols: int = 80, rows: int = 24) -> PtyBridge:
    return PtyBridge.spawn(terminal_argv(), cwd=str(terminal_home()), env=terminal_environment(), cols=cols, rows=rows)


def websocket_authorized(websocket: WebSocket) -> bool:
    """Use Hermes' canonical dashboard WebSocket authorization check."""
    return bool(_ws_auth_ok(websocket))


def _message_payload(message: dict[str, Any]) -> str | None:
    raw = message.get("text")
    if isinstance(raw, str):
        return raw
    raw = message.get("bytes")
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    return None


async def _send_error(websocket: WebSocket, message: str) -> None:
    await websocket.send_json({"type": "error", "message": message})


async def _pump_output(websocket: WebSocket, bridge: PtyBridge) -> None:
    while bridge.is_alive():
        data = await asyncio.to_thread(bridge.read, 0.2)
        if data is None:
            return
        if data:
            await websocket.send_bytes(data)


async def _handle_input(websocket: WebSocket, bridge: PtyBridge) -> None:
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        raw = _message_payload(message)
        if raw is None:
            await _send_error(websocket, "Terminal messages must be UTF-8 JSON.")
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            await _send_error(websocket, "Terminal message must be JSON.")
            continue
        if not isinstance(payload, dict):
            await _send_error(websocket, "Terminal message must be an object.")
            continue
        if payload.get("type") == "input":
            data = payload.get("data")
            if not isinstance(data, str) or len(data.encode("utf-8")) > _MAX_INPUT_BYTES:
                await _send_error(websocket, "Terminal input is invalid or too large.")
                continue
            if not await bridge.write(data.encode("utf-8")):
                await _send_error(websocket, "Terminal shell is no longer available.")
                return
            continue
        if payload.get("type") == "resize":
            cols, rows = payload.get("cols"), payload.get("rows")
            if not isinstance(cols, int) or not isinstance(rows, int):
                await _send_error(websocket, "Terminal resize requires integer cols and rows.")
                continue
            bridge.resize(cols=cols, rows=rows)
            continue
        await _send_error(websocket, "Unsupported terminal message.")


@router.websocket("/terminal")
async def terminal_websocket(websocket: WebSocket) -> None:
    """Attach one dashboard client to one short-lived interactive shell PTY."""
    if not websocket_authorized(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    log.info("[ha-terminal] terminal websocket connected")
    bridge: PtyBridge | None = None
    output_task: asyncio.Task[None] | None = None
    input_task: asyncio.Task[None] | None = None
    try:
        bridge = spawn_terminal()
        log.info("[ha-terminal] spawned PTY pid=%s", bridge.pid)
        output_task = asyncio.create_task(_pump_output(websocket, bridge))
        input_task = asyncio.create_task(_handle_input(websocket, bridge))
        await asyncio.wait({output_task, input_task}, return_when=asyncio.FIRST_COMPLETED)
        if not bridge.is_alive():
            await _send_error(websocket, "Terminal shell exited. Start a new terminal to reconnect.")
            await websocket.close()
    except PtyUnavailableError:
        await _send_error(websocket, "A pseudo-terminal is unavailable in this container.")
    except (FileNotFoundError, OSError):
        await _send_error(websocket, "The container shell could not be started.")
    except WebSocketDisconnect:
        pass
    finally:
        for task in (output_task, input_task):
            if task is not None:
                task.cancel()
        for task in (output_task, input_task):
            if task is not None:
                with suppress(asyncio.CancelledError):
                    await task
        if bridge is not None:
            await asyncio.to_thread(bridge.close)
        log.info("[ha-terminal] terminal websocket disconnected")
