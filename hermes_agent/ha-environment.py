#!/usr/bin/env python3
"""Materialize the three Home Assistant integration options into s6 env."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


STANDARD_OPTIONS = Path("/data/options.json")
MAPPED_OPTIONS = Path("/opt/data/options.json")
S6_ENVIRONMENT = Path("/run/s6/container_environment")


def fail(message: str) -> None:
    print(f"[ha-environment] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def same_file(first: Path, second: Path) -> bool:
    try:
        return first.samefile(second)
    except OSError:
        return False


def options_path() -> Path:
    standard_exists = STANDARD_OPTIONS.is_file()
    mapped_exists = MAPPED_OPTIONS.is_file()
    if standard_exists and mapped_exists and not same_file(STANDARD_OPTIONS, MAPPED_OPTIONS):
        fail("found conflicting Home Assistant options files")
    if standard_exists:
        return STANDARD_OPTIONS
    if mapped_exists:
        return MAPPED_OPTIONS
    fail("Home Assistant options.json was not found")


def load_options() -> dict[str, Any]:
    try:
        options = json.loads(options_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("could not read Home Assistant options.json")
    if not isinstance(options, dict):
        fail("Home Assistant options.json must contain an object")
    return options


def string_option(options: dict[str, Any], name: str) -> str:
    value = options.get(name, "")
    if not isinstance(value, str):
        fail(f"{name} must be a string")
    if "\x00" in value or "\n" in value or "\r" in value:
        fail(f"{name} must not contain control characters")
    return value


def validate_hass_url(value: str) -> None:
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.params or parsed.query or parsed.fragment:
        fail("hass_url must be an http(s) Home Assistant Core base URL")
    if parsed.path not in {"", "/"}:
        fail("hass_url must not include an API path")


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


def remove_s6_environment(name: str) -> None:
    try:
        (S6_ENVIRONMENT / name).unlink(missing_ok=True)
    except OSError:
        fail(f"could not clear runtime environment for {name}")


def configure_environment(options: dict[str, Any]) -> None:
    hass_url = string_option(options, "hass_url").rstrip("/")
    hass_token = string_option(options, "hass_token")
    api_server_key = string_option(options, "api_server_key")
    validate_hass_url(hass_url)
    if not api_server_key.strip():
        fail("api_server_key is required; configure an OpenAI-compatible API key before starting")

    if hass_url:
        write_s6_environment("HASS_URL", hass_url)
        print("[ha-environment] HASS_URL configured")
    else:
        remove_s6_environment("HASS_URL")
        print("[ha-environment] HASS_URL not set; Hermes will use its upstream default")

    if hass_token:
        write_s6_environment("HASS_TOKEN", hass_token)
        print("[ha-environment] HASS_TOKEN configured")
    else:
        remove_s6_environment("HASS_TOKEN")
        print("[ha-environment] WARNING: HASS_TOKEN is not configured; Hermes Home Assistant integration is unavailable", file=sys.stderr)

    write_s6_environment("API_SERVER_KEY", api_server_key)
    print("[ha-environment] API_SERVER_KEY configured")
    print("[ha-environment] Official Home Assistant CLI is available at /usr/local/bin/ha")


def main() -> None:
    print("[ha-environment] Hermes Home Assistant app initialization")
    configure_environment(load_options())


if __name__ == "__main__":
    main()
