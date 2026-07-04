#!/usr/bin/env python3
"""Activate or restore a versioned production virtual environment safely."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


class EnvironmentFailure(RuntimeError):
    """A release environment transition could not complete safely."""


def require_directory(path: Path, label: str) -> None:
    if not path.is_dir():
        raise EnvironmentFailure(f"{label} does not exist or is not a directory: {path}")


def activate(active: Path, release: Path, rollback: Path) -> None:
    require_directory(active, "Active environment")
    require_directory(release, "Release environment")
    if rollback.exists():
        raise EnvironmentFailure(f"Rollback environment already exists: {rollback}")

    active.rename(rollback)
    try:
        release.rename(active)
    except OSError:
        rollback.rename(active)
        raise
    print(f"Activated release environment: {active}")


def rollback(active: Path, rollback_path: Path, failed: Path) -> None:
    if not rollback_path.exists():
        print("Rollback environment is absent; activation did not complete, nothing to restore.")
        return
    require_directory(rollback_path, "Rollback environment")
    if failed.exists():
        raise EnvironmentFailure(f"Failed-release destination already exists: {failed}")

    moved_active = False
    if active.exists():
        require_directory(active, "Active environment")
        active.rename(failed)
        moved_active = True
    try:
        rollback_path.rename(active)
    except OSError:
        if moved_active:
            failed.rename(active)
        raise
    print(f"Restored rollback environment: {active}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("--active", type=Path, required=True)
    activate_parser.add_argument("--release", type=Path, required=True)
    activate_parser.add_argument("--rollback", type=Path, required=True)

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--active", type=Path, required=True)
    rollback_parser.add_argument("--rollback", type=Path, required=True)
    rollback_parser.add_argument("--failed", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "activate":
            activate(args.active, args.release, args.rollback)
        else:
            rollback(args.active, args.rollback, args.failed)
    except (EnvironmentFailure, OSError) as exc:
        print(f"Release environment transition failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
