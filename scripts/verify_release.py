#!/usr/bin/env python3
"""Verify a staged production release without inline remote Python programs."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EXPECTED_DIMENSION = 384


class VerificationFailure(RuntimeError):
    """A staged release failed a production verification."""


def verify_model(model_name: str, cache_dir: Path, expected_dimension: int) -> None:
    os.environ["HF_HOME"] = str(cache_dir)

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, device="cpu")
    if model.device.type != "cpu":
        raise VerificationFailure(
            f"Expected CPU model execution, got device {model.device.type!r}."
        )

    embeddings = model.encode(["production CPU smoke test"])
    expected_shape = (1, expected_dimension)
    if embeddings.shape != expected_shape:
        raise VerificationFailure(
            f"Expected embedding shape {expected_shape}, got {embeddings.shape}."
        )

    print(
        f"CPU model verification passed: {model_name}, "
        f"embedding dimension {expected_dimension}."
    )


def verify_backend_import(module_name: str) -> None:
    repo = str(REPO_ROOT)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    importlib.import_module(module_name)
    print(f"Backend import verification passed: {module_name}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    model = subparsers.add_parser("model", help="Initialize and exercise the CPU model.")
    model.add_argument("--model", default=DEFAULT_MODEL)
    model.add_argument("--cache-dir", type=Path, required=True)
    model.add_argument(
        "--expected-dimension", type=int, default=DEFAULT_EXPECTED_DIMENSION
    )

    backend = subparsers.add_parser(
        "backend-import", help="Import the configured backend application module."
    )
    backend.add_argument("--module", default="backend.main")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "model":
            if args.expected_dimension <= 0:
                raise VerificationFailure("Expected dimension must be positive.")
            verify_model(args.model, args.cache_dir.resolve(), args.expected_dimension)
        else:
            verify_backend_import(args.module)
    except (ImportError, VerificationFailure) as exc:
        print(f"Release verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
