#!/usr/bin/env python3
"""Apply one verified Hermes stable-release update to add-on metadata."""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path


TAG_PATTERN = re.compile(r"^v(?P<version>\d{4}\.\d+\.\d+)$")
FROM_PATTERN = re.compile(r"^(FROM nousresearch/hermes-agent:)([^\s]+)(.*)$", re.MULTILINE)


def _write_if_changed(path: Path, content: str) -> bool:
    if path.read_text(encoding="utf-8") == content:
        return False
    mode = path.stat().st_mode & 0o777
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.chmod(mode)
    temporary_path.replace(path)
    return True


def update_release(dockerfile: Path, config: Path, changelog: Path, tag: str) -> bool:
    """Update the image references, add-on version, and changelog exactly once."""
    match = TAG_PATTERN.fullmatch(tag)
    if not match:
        raise ValueError(f"Unsupported Hermes stable tag: {tag!r}")

    addon_version = f"{match.group('version')}-1"
    heading = f"## {addon_version}"
    entry = f"- Upgraded Hermes container to stable version {tag}."

    dockerfile_text = dockerfile.read_text(encoding="utf-8")
    from_matches = FROM_PATTERN.findall(dockerfile_text)
    if len(from_matches) != 2:
        raise ValueError(f"Expected exactly two Hermes FROM lines, found {len(from_matches)}")
    current_tags = {match[1] for match in from_matches}
    if len(current_tags) != 1:
        raise ValueError(f"Hermes FROM lines disagree: {sorted(current_tags)}")
    # The workflow normally prevents this call for an unchanged image tag. Keep
    # the transform safe when invoked directly too: local add-on revisions such
    # as 2026.9.24-2 must never be reset to the upstream -1 revision.
    if current_tags == {tag}:
        return False
    updated_dockerfile = FROM_PATTERN.sub(rf"\g<1>{tag}\g<3>", dockerfile_text)

    config_text = config.read_text(encoding="utf-8")
    updated_config, version_count = re.subn(
        r'^version: ".*"$', f'version: "{addon_version}"', config_text, count=1, flags=re.MULTILINE
    )
    if version_count != 1:
        raise ValueError("Expected exactly one quoted add-on version in config.yaml")

    changelog_text = changelog.read_text(encoding="utf-8")
    if not changelog_text.startswith("# Changelog\n"):
        raise ValueError("CHANGELOG.md must begin with '# Changelog'")
    section_pattern = re.compile(rf"^{re.escape(heading)}$", re.MULTILINE)
    heading_matches = list(section_pattern.finditer(changelog_text))
    if len(heading_matches) > 1:
        raise ValueError(f"Duplicate changelog heading: {heading}")
    if heading_matches:
        section_start = heading_matches[0].end()
        next_heading = re.search(r"^## ", changelog_text[section_start:], re.MULTILINE)
        section_end = section_start + next_heading.start() if next_heading else len(changelog_text)
        section = changelog_text[section_start:section_end]
        if entry not in section:
            raise ValueError(f"Existing changelog section {heading} does not contain the expected upgrade entry")
        updated_changelog = changelog_text
    else:
        updated_changelog = f"# Changelog\n\n{heading}\n\n{entry}\n" + changelog_text[len("# Changelog\n") :]

    changes = [
        _write_if_changed(path, content)
        for path, content in (
            (dockerfile, updated_dockerfile),
            (config, updated_config),
            (changelog, updated_changelog),
        )
    ]
    return any(changes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="stable Hermes tag, for example v2026.9.24")
    parser.add_argument("--dockerfile", type=Path, default=Path("hermes_agent/Dockerfile"))
    parser.add_argument("--config", type=Path, default=Path("hermes_agent/config.yaml"))
    parser.add_argument("--changelog", type=Path, default=Path("hermes_agent/CHANGELOG.md"))
    args = parser.parse_args()
    try:
        update_release(args.dockerfile, args.config, args.changelog, args.tag)
    except (OSError, ValueError) as error:
        print(f"Hermes release update failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
