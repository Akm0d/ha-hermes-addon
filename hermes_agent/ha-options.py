#!/usr/bin/env python3
"""Apply the two Home Assistant options before Hermes' own cont-init hook."""

from __future__ import annotations

import os
import pwd
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml


HERMES_HOME = Path("/opt/data")
STANDARD_OPTIONS = Path("/data/options.json")
MAPPED_OPTIONS = HERMES_HOME / "options.json"
REAL_HA = Path("/usr/local/lib/hermes-ha-cli/ha")
OPTIONS_PATH_RECORD = Path("/run/hermes-ha-options-path")


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
        fail("found conflicting Home Assistant options files at /data/options.json and /opt/data/options.json")
    if standard_exists:
        return STANDARD_OPTIONS
    if mapped_exists:
        return MAPPED_OPTIONS
    fail("Home Assistant options.json was not found at /data/options.json or /opt/data/options.json")


def load_options(path: Path) -> dict[str, Any]:
    try:
        import json

        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("could not read Home Assistant options.json")
    if not isinstance(loaded, dict):
        fail("Home Assistant options.json must contain an object")
    return loaded


def validate_config(raw: str) -> None:
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError:
        fail("config_yaml must be valid YAML with a mapping at its document root")
    if not isinstance(loaded, dict):
        fail("config_yaml must be valid YAML with a mapping at its document root")


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


def apply_ha_cli_gate(enabled: bool) -> None:
    if not REAL_HA.is_file():
        fail("the bundled Home Assistant CLI is missing")
    if enabled:
        os.chmod(REAL_HA, 0o755)
    else:
        # Hermes runs as the non-root hermes user, so mode 0700 prevents both
        # PATH and absolute-path execution while retaining a root-only binary.
        os.chmod(REAL_HA, 0o700)


def main() -> None:
    source = options_path()
    options = load_options(source)
    enabled = options.get("enable_ha_cli", False)
    raw_config = options.get("config_yaml", "{}")
    if not isinstance(enabled, bool):
        fail("enable_ha_cli must be a boolean")
    if not isinstance(raw_config, str):
        fail("config_yaml must be a string")
    validate_config(raw_config)
    write_config(raw_config)
    apply_ha_cli_gate(enabled)
    OPTIONS_PATH_RECORD.write_text(f"{source}\n", encoding="utf-8")
    os.chmod(OPTIONS_PATH_RECORD, 0o600)
    print(f"[ha-options] Applied config_yaml and {'enabled' if enabled else 'disabled'} the Home Assistant CLI")


if __name__ == "__main__":
    main()
