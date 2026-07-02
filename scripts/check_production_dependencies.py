#!/usr/bin/env python3
"""Resolve and validate the Linux Python 3.13 production dependency set."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_REQUIREMENTS = REPO_ROOT / "requirements-production.txt"
DEFAULT_BUDGET_BYTES = 3 * 1024**3
DEFAULT_REQUIRED_FREE_BYTES = 4 * 1024**3
GPU_PACKAGE_MARKERS = (
    "cuda",
    "cublas",
    "cudnn",
    "nccl",
    "nvshmem",
    "nvidia",
    "triton",
)


class CheckFailure(RuntimeError):
    """A production dependency policy violation."""


def canonicalize(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def wheel_identity(path: Path) -> tuple[str, str]:
    parts = path.name[:-4].split("-")
    if len(parts) < 5:
        raise CheckFailure(f"Cannot inspect malformed wheel filename: {path.name}")
    return canonicalize(parts[0]), parts[1]


def installed_wheel_bytes(path: Path) -> int:
    try:
        with zipfile.ZipFile(path) as wheel:
            return sum(member.file_size for member in wheel.infolist())
    except zipfile.BadZipFile as exc:
        raise CheckFailure(f"Cannot inspect invalid wheel archive: {path.name}") from exc


def validate_wheels(wheel_dir: Path, budget_bytes: int) -> tuple[int, int]:
    wheels = sorted(wheel_dir.glob("*.whl"))
    if not wheels:
        raise CheckFailure(f"No wheels were resolved in {wheel_dir}")

    packages = [wheel_identity(wheel) for wheel in wheels]
    gpu_packages = sorted(
        name for name, _ in packages if any(marker in name for marker in GPU_PACKAGE_MARKERS)
    )
    if gpu_packages:
        raise CheckFailure(
            "Resolved GPU runtime packages: "
            + ", ".join(gpu_packages)
            + ". Keep torch pinned to the +cpu build in requirements-production.txt."
        )

    torch_versions = [version for name, version in packages if name == "torch"]
    if torch_versions != ["2.10.0+cpu"]:
        resolved = ", ".join(torch_versions) if torch_versions else "not resolved"
        raise CheckFailure(
            f"Expected torch 2.10.0+cpu, but Torch was {resolved}. "
            "Restore the official hash-pinned PyTorch CPU wheel."
        )

    installed_bytes = sum(installed_wheel_bytes(wheel) for wheel in wheels)
    if installed_bytes > budget_bytes:
        raise CheckFailure(
            f"Resolved install is {installed_bytes:,} bytes, which exceeds the production "
            f"dependency budget of {budget_bytes:,} bytes."
        )
    return len(wheels), installed_bytes


def resolve_wheels(wheel_dir: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--requirement",
        str(PRODUCTION_REQUIREMENTS),
        "--dest",
        str(wheel_dir),
        "--platform",
        "manylinux_2_28_x86_64",
        "--platform",
        "manylinux2014_x86_64",
        "--platform",
        "manylinux_2_17_x86_64",
        "--platform",
        "linux_x86_64",
        "--python-version",
        "3.13",
        "--implementation",
        "cp",
        "--abi",
        "cp313",
        "--only-binary",
        ":all:",
    ]
    try:
        subprocess.run(command, cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        raise CheckFailure(
            "Linux Python 3.13 dependency resolution failed. "
            "Run this command with network access and inspect pip's error above."
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel-dir",
        type=Path,
        help="Validate an existing resolved wheel directory instead of resolving dependencies.",
    )
    parser.add_argument(
        "--budget-bytes",
        type=int,
        default=DEFAULT_BUDGET_BYTES,
        help="Maximum expanded wheel payload size.",
    )
    parser.add_argument(
        "--check-path",
        type=Path,
        default=REPO_ROOT,
        help="Filesystem whose free capacity must satisfy the production headroom policy.",
    )
    parser.add_argument(
        "--required-free-bytes",
        type=int,
        default=DEFAULT_REQUIRED_FREE_BYTES,
        help="Required free bytes before dependency resolution; use 0 for fixture validation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.budget_bytes <= 0 or args.required_free_bytes < 0:
        print("Storage limits must be positive.", file=sys.stderr)
        return 2

    if args.wheel_dir is None:
        free_bytes = shutil.disk_usage(args.check_path).free
        if free_bytes < args.required_free_bytes:
            print(
                f"Only {free_bytes:,} bytes are free on {args.check_path}; "
                f"{args.required_free_bytes:,} bytes are required before creating a release "
                "virtualenv. Remove only an incomplete .venv.release-* directory, never .venv.",
                file=sys.stderr,
            )
            return 1

    try:
        if args.wheel_dir is not None:
            wheel_count, installed_bytes = validate_wheels(
                args.wheel_dir, args.budget_bytes
            )
        else:
            with tempfile.TemporaryDirectory(
                prefix=".webchat-production-wheels-", dir=args.check_path
            ) as tmp:
                wheel_dir = Path(tmp)
                resolve_wheels(wheel_dir)
                wheel_count, installed_bytes = validate_wheels(
                    wheel_dir, args.budget_bytes
                )
    except CheckFailure as exc:
        print(f"Production dependency check failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Production dependency check passed: {wheel_count} wheels, "
        f"{installed_bytes:,} installed bytes, CPU-only Torch 2.10.0+cpu."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
