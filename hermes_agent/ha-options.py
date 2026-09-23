#!/usr/bin/env python3
"""Mirror native Hermes config.yaml and the single Supervisor option."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


HERMES_HOME = Path("/opt/data")
CONFIG_PATH = HERMES_HOME / "config.yaml"
STANDARD_OPTIONS = Path("/data/options.json")
MAPPED_OPTIONS = HERMES_HOME / "options.json"
POLL_SECONDS = 2
MIRROR_SETTLE_SECONDS = 10


def fail(message: str) -> None:
    print(f"[ha-config-sync] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_mapping(value: Any, message: str) -> None:
    if not isinstance(value, dict):
        fail(message)


def validate_config(raw: str) -> None:
    try:
        loaded = yaml.safe_load(raw)
    except yaml.YAMLError:
        fail("native /opt/data/config.yaml must be valid YAML with a mapping at its document root")
    require_mapping(loaded, "native /opt/data/config.yaml must be valid YAML with a mapping at its document root")


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


def load_options(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("could not read Home Assistant options.json")
    require_mapping(loaded, "Home Assistant options.json must contain an object")
    return loaded


def option_config(options: dict[str, Any]) -> str:
    raw = options.get("config_yaml", "{}\n")
    if not isinstance(raw, str):
        fail("config_yaml must be a string")
    return raw


def read_native_config() -> str:
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8")
    except OSError:
        fail("could not read native /opt/data/config.yaml after Hermes initialization")
    validate_config(raw)
    return raw


def write_native_config(raw: str) -> None:
    validate_config(raw)
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
            os.replace(temporary, CONFIG_PATH)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    except OSError:
        fail("could not atomically write native /opt/data/config.yaml")


def supervisor_post(path: str, payload: dict[str, Any]) -> bool:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        print("[ha-config-sync] WARNING: SUPERVISOR_TOKEN is unavailable", file=sys.stderr)
        return False
    request = urllib.request.Request(
        f"http://supervisor{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.HTTPError):
        return False


def mirror_native_to_options(raw: str) -> bool:
    if not supervisor_post("/addons/self/options", {"options": {"config_yaml": raw}}):
        print("[ha-config-sync] WARNING: could not mirror native config to Home Assistant options", file=sys.stderr)
        return False
    print("[ha-config-sync] Mirrored native /opt/data/config.yaml to Home Assistant options")
    return True


def request_restart() -> bool:
    if not supervisor_post("/addons/self/restart", {}):
        print("[ha-config-sync] ERROR: native config was updated but Supervisor restart request failed", file=sys.stderr)
        return False
    print("[ha-config-sync] Home Assistant config_yaml changed; requested Supervisor-managed restart")
    return True


def digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def startup() -> None:
    """Run after upstream Hermes initialization has seeded native state."""
    raw = read_native_config()
    if not mirror_native_to_options(raw):
        fail("could not mirror native /opt/data/config.yaml to Home Assistant options")
    print("[ha-config-sync] Validated native /opt/data/config.yaml after Hermes initialization")


def watch() -> None:
    source = options_path()
    native = read_native_config()
    native_hash = digest(native)
    expected_option_hash = native_hash
    settle_until = time.monotonic() + MIRROR_SETTLE_SECONDS
    restart_pending = False
    print("[ha-config-sync] Watching native config and Home Assistant config_yaml")

    while True:
        time.sleep(POLL_SECONDS)
        try:
            current_native = read_native_config()
            current_option = option_config(load_options(source))
        except SystemExit:
            # Native state is authoritative. Do not overwrite malformed direct
            # edits from the mirror; Hermes will surface them in its own logs.
            continue

        current_native_hash = digest(current_native)
        current_option_hash = digest(current_option)
        if restart_pending:
            if request_restart():
                return
            continue
        if current_native_hash != native_hash:
            if mirror_native_to_options(current_native):
                native_hash = current_native_hash
                expected_option_hash = current_native_hash
                settle_until = time.monotonic() + MIRROR_SETTLE_SECONDS
            continue

        if current_option_hash == expected_option_hash or time.monotonic() < settle_until:
            continue
        try:
            validate_config(current_option)
        except SystemExit:
            if mirror_native_to_options(current_native):
                expected_option_hash = native_hash
                settle_until = time.monotonic() + MIRROR_SETTLE_SECONDS
            continue

        write_native_config(current_option)
        native_hash = digest(current_option)
        expected_option_hash = native_hash
        restart_pending = True
        # Stop after a successful request so this process cannot create a
        # second restart loop while Supervisor stops the app.
        if request_restart():
            return
        settle_until = time.monotonic() + MIRROR_SETTLE_SECONDS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true")
    if parser.parse_args().watch:
        watch()
    else:
        startup()


if __name__ == "__main__":
    main()
