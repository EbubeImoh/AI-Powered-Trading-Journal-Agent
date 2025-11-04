"""Utility for verifying that required environment configuration is intact.

The tool performs two main checks:

1. It attempts to instantiate ``AppSettings`` using the provided ``.env`` file,
   surfacing missing or malformed configuration entries before the services
   start failing.
2. It can record and verify a checksum for the ``.env`` file so unexpected
   edits (for example, from an accidental ``git pull``) are detected.

Example usages::

    # Validate required settings are present and record the expected checksum.
    python -m scripts.check_env record --env-file /opt/pecunia/.env \
        --hash-file /opt/pecunia/.env.sha256

    # Run later (e.g. from cron/systemd) to alert on drift.
    python -m scripts.check_env verify --env-file /opt/pecunia/.env \
        --hash-file /opt/pecunia/.env.sha256
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from app.core.config import AppSettings, _load_env_file

EXIT_OK = 0
EXIT_VALIDATION_ERROR = 2
EXIT_CHECKSUM_ERROR = 3
EXIT_RUNTIME_ERROR = 5


def _compute_hash(env_file: Path) -> str:
    """Return the SHA256 checksum for the target environment file."""
    return hashlib.sha256(env_file.read_bytes()).hexdigest()


def _validate_settings(env_file: Path) -> None:
    """Ensure required settings can be loaded from the supplied env file."""
    _load_env_file(str(env_file))
    AppSettings()  # type: ignore[call-arg]


def _record_checksum(env_file: Path, hash_file: Path) -> int:
    """Persist the current checksum to ``hash_file``."""
    checksum = _compute_hash(env_file)
    hash_file.write_text(f"{checksum}\n", encoding="utf-8")
    print(f"Recorded checksum to {hash_file} ({checksum})")
    return EXIT_OK


def _verify_checksum(env_file: Path, hash_file: Path) -> int:
    """Compare the current checksum to the recorded baseline."""
    if not hash_file.exists():
        print(
            f"Expected checksum file {hash_file} is missing. "
            "Re-run with the 'record' command to establish a baseline.",
            file=sys.stderr,
        )
        return EXIT_RUNTIME_ERROR

    expected = hash_file.read_text(encoding="utf-8").strip()
    actual = _compute_hash(env_file)
    if expected == actual:
        print("Environment checksum OK.")
        return EXIT_OK

    print(
        "Environment checksum mismatch!\n"
        f"  expected: {expected}\n"
        f"  actual:   {actual}\n"
        "Investigate recent changes before restarting services.",
        file=sys.stderr,
    )
    return EXIT_CHECKSUM_ERROR


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate required settings and detect .env drift."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_arguments(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument(
            "--env-file",
            default=".env",
            type=Path,
            help="Path to the environment file (default: .env in the repo root).",
        )

    record_parser = subparsers.add_parser(
        "record",
        help="Validate settings and store the checksum baseline.",
    )
    add_common_arguments(record_parser)
    record_parser.add_argument(
        "--hash-file",
        required=True,
        type=Path,
        help="Location to write the checksum baseline.",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Validate settings and compare the checksum with the baseline.",
    )
    add_common_arguments(verify_parser)
    verify_parser.add_argument(
        "--hash-file",
        required=True,
        type=Path,
        help="Location of the previously recorded checksum baseline.",
    )

    check_parser = subparsers.add_parser(
        "check",
        help="Validate settings without touching any checksum files.",
    )
    add_common_arguments(check_parser)

    return parser


def _ensure_env_file(env_file: Path) -> None:
    if not env_file.exists():
        raise FileNotFoundError(
            f"Environment file {env_file} does not exist. "
            "Ensure the path is correct or create it before running this tool."
        )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    env_file: Path = args.env_file

    try:
        _ensure_env_file(env_file)
        _validate_settings(env_file)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    except ValidationError as exc:
        print(
            "Settings validation failed. Missing or invalid values detected:\n"
            f"{exc.json(indent=2)}",
            file=sys.stderr,
        )
        return EXIT_VALIDATION_ERROR
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Unexpected error during validation: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR

    command: str = args.command
    handlers: dict[str, Callable[[], int]] = {
        "record": lambda: _record_checksum(env_file, args.hash_file),
        "verify": lambda: _verify_checksum(env_file, args.hash_file),
        "check": lambda: EXIT_OK,
    }
    return handlers[command]()


if __name__ == "__main__":  # pragma: no cover - script entry point
    sys.exit(main())
