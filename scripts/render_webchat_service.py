#!/usr/bin/env python3
"""Render the tracked systemd unit template with validated deployment values."""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path


DEPLOY_USER = re.compile(r"^[a-z_][a-z0-9_-]*\$?$")
USER_PLACEHOLDER = "<deploy-user>"
DIRECTORY_PLACEHOLDER = "<deploy-dir>"


class RenderFailure(RuntimeError):
    """The systemd unit could not be rendered safely."""


def validate_values(deploy_user: str, deploy_dir: Path) -> None:
    if not DEPLOY_USER.fullmatch(deploy_user):
        raise RenderFailure(f"Invalid deployment user: {deploy_user!r}.")
    if not deploy_dir.is_absolute():
        raise RenderFailure("Deployment directory must be absolute.")
    if any(character.isspace() or ord(character) < 32 for character in str(deploy_dir)):
        raise RenderFailure("Deployment directory cannot contain whitespace or controls.")


def render(template: Path, deploy_user: str, deploy_dir: Path) -> str:
    validate_values(deploy_user, deploy_dir)
    source = template.read_text(encoding="utf-8")
    if USER_PLACEHOLDER not in source or DIRECTORY_PLACEHOLDER not in source:
        raise RenderFailure("Service template is missing required placeholders.")

    rendered = source.replace(USER_PLACEHOLDER, deploy_user).replace(
        DIRECTORY_PLACEHOLDER, str(deploy_dir)
    )
    if "<deploy-" in rendered:
        raise RenderFailure("Rendered service unit contains unresolved placeholders.")
    return rendered


def write_atomic(output: Path, content: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", dir=output.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o644)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deploy-user", required=True)
    parser.add_argument("--deploy-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rendered = render(args.template, args.deploy_user, args.deploy_dir)
        write_atomic(args.output, rendered)
    except (OSError, RenderFailure) as exc:
        print(f"Service-unit render failed: {exc}", file=sys.stderr)
        return 1
    print(f"Rendered systemd unit: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
