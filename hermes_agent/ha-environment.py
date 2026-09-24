#!/usr/bin/env python3
"""Materialize the Home Assistant API bearer key into the s6 environment."""

from __future__ import annotations

import json
import os
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SUPERVISOR_URL = "http://supervisor"
INFO_PATH = "/addons/self/info"
OPTIONS_PATH = "/addons/self/options"
S6_ENVIRONMENT = Path("/run/s6/container_environment")


def fail(message: str) -> None:
    print(f"[ha-environment] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def supervisor_token() -> str:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        fail("SUPERVISOR_TOKEN is unavailable; cannot read Home Assistant app options")
    return token


def supervisor_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{SUPERVISOR_URL}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {supervisor_token()}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, UnicodeDecodeError, ValueError):
        fail("Supervisor app-options request failed")
    if not isinstance(body, dict) or body.get("result") != "ok":
        fail("Supervisor returned an invalid app-options response")
    return body


def load_options() -> dict[str, Any]:
    response = supervisor_request("GET", INFO_PATH)
    data = response.get("data")
    options = data.get("options") if isinstance(data, dict) else None
    if not isinstance(options, dict):
        fail("Supervisor returned invalid app options")
    return options


def persist_options(options: dict[str, str]) -> None:
    supervisor_request("POST", OPTIONS_PATH, {"options": options})


def option_key(options: dict[str, Any]) -> str | None:
    key = options.get("api_server_key")
    if not isinstance(key, str) or not key.strip():
        return None
    if "\x00" in key or "\n" in key or "\r" in key:
        return None
    return key


def resolve_api_key(options: dict[str, Any]) -> str:
    key = option_key(options)
    generated = key is None
    if generated:
        key = secrets.token_urlsafe(32)

    clean_options = {"api_server_key": key}
    if generated or options != clean_options:
        try:
            persist_options(clean_options)
        except SystemExit:
            if generated:
                raise
            print(
                "[ha-environment] WARNING: could not remove obsolete Home Assistant app options; using existing API_SERVER_KEY",
                file=sys.stderr,
            )
        else:
            if generated:
                print("[ha-environment] API_SERVER_KEY generated and persisted")
            else:
                print("[ha-environment] obsolete Home Assistant app options removed")
    else:
        print("[ha-environment] API_SERVER_KEY loaded from Supervisor options")

    return key


def write_s6_environment(name: str, value: str) -> None:
    target = S6_ENVIRONMENT / name
    try:
        S6_ENVIRONMENT.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=S6_ENVIRONMENT)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    except OSError:
        fail(f"could not set runtime environment for {name}")


def configure_environment() -> None:
    write_s6_environment("API_SERVER_KEY", resolve_api_key(load_options()))
    print("[ha-environment] API_SERVER_KEY configured for s6 services")
    print("[ha-environment] Official Home Assistant CLI is available at /usr/local/bin/ha")


def main() -> None:
    print("[ha-environment] Hermes Home Assistant app initialization")
    configure_environment()


if __name__ == "__main__":
    main()
