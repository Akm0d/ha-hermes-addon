#!/usr/bin/env python3
"""Materialize the one Home Assistant option before Hermes' cont-init hook."""

from __future__ import annotations

import json
import os
import pwd
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


HERMES_HOME = Path("/opt/data")
STANDARD_OPTIONS = Path("/data/options.json")
MAPPED_OPTIONS = HERMES_HOME / "options.json"
LEGACY_OPTIONS = frozenset(
    {
        "enable_ha_cli",
        "timezone",
        "model_provider",
        "model_name",
        "model_base_url",
        "openrouter_api_key",
        "google_api_key",
        "anthropic_api_key",
        "openai_api_key",
        "enable_dashboard_tui",
        "enable_terminal",
        "gateway_timeout",
    }
)


def fail(message: str) -> None:
    print(f"[ha-options] ERROR: {message}", file=sys.stderr)
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
    if MAPPED_OPTIONS.is_file():
        return MAPPED_OPTIONS
    fail("Home Assistant options.json was not found")


def load_options(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("could not read Home Assistant options.json")
    require_mapping(loaded, "Home Assistant options.json must contain an object")
    return loaded


def validate_config(raw: str) -> None:
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError:
        fail("config_yaml must be valid YAML with a mapping at its document root")
    require_mapping(loaded, "config_yaml must be valid YAML with a mapping at its document root")


def require_mapping(value: Any, message: str) -> None:
    if not isinstance(value, dict):
        fail(message)


def legacy_config_yaml(options: dict[str, Any], raw: str | None) -> str:
    """Preserve verified legacy model settings only when native YAML is empty."""
    if raw is not None:
        try:
            if yaml.safe_load(raw) != {}:
                return raw
        except yaml.YAMLError:
            return raw

    model: dict[str, str] = {}
    for old_key, native_key in (
        ("model_provider", "provider"),
        ("model_name", "default"),
        ("model_base_url", "base_url"),
    ):
        value = options.get(old_key)
        if isinstance(value, str) and value.strip():
            model[native_key] = value.strip()
    if not model:
        return raw if raw is not None else "{}\n"
    return yaml.safe_dump({"model": model}, sort_keys=False, allow_unicode=False)


def write_config(raw: str) -> None:
    try:
        hermes = pwd.getpwnam("hermes")
        HERMES_HOME.mkdir(mode=0o750, parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=".config.yaml.", dir=HERMES_HOME)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(raw)
                if not raw.endswith("\n"):
                    stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chown(temporary, hermes.pw_uid, hermes.pw_gid)
            os.chmod(temporary, 0o640)
            os.replace(temporary, HERMES_HOME / "config.yaml")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    except OSError:
        fail("could not atomically write /opt/data/config.yaml")


def remove_legacy_options(options: dict[str, Any], raw_config: str) -> None:
    if not (LEGACY_OPTIONS & options.keys()):
        return
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        print("[ha-options] WARNING: obsolete options remain because SUPERVISOR_TOKEN is unavailable", file=sys.stderr)
        return
    payload = json.dumps({"options": {"config_yaml": raw_config}}).encode("utf-8")
    request = urllib.request.Request(
        "http://supervisor/addons/self/options",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                raise urllib.error.HTTPError(request.full_url, response.status, "", response.headers, None)
    except (OSError, urllib.error.HTTPError):
        print("[ha-options] WARNING: could not remove obsolete Home Assistant options; retrying next startup", file=sys.stderr)
        return
    print("[ha-options] Removed obsolete Home Assistant options")


def main() -> None:
    source = options_path()
    options = load_options(source)
    configured = options.get("config_yaml")
    if configured is not None and not isinstance(configured, str):
        fail("config_yaml must be a string")
    raw_config = legacy_config_yaml(options, configured)
    if not isinstance(raw_config, str):
        fail("config_yaml must be a string")
    validate_config(raw_config)
    write_config(raw_config)
    remove_legacy_options(options, raw_config)
    print("[ha-options] Validated config_yaml and wrote /opt/data/config.yaml")


if __name__ == "__main__":
    main()
