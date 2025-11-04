"""Tests for the environment drift detection script."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_env

REQUIRED_ENV_KEYS = [
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GOOGLE_REDIRECT_URI",
    "ANALYSIS_QUEUE_URL",
    "DYNAMODB_TABLE_NAME",
    "GEMINI_API_KEY",
]


def _write_env(env_path: Path, **values: str) -> None:
    contents = "\n".join(f"{key}={value}" for key, value in values.items())
    env_path.write_text(contents + "\n", encoding="utf-8")


def _clear_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in REQUIRED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("command", ["record", "verify", "check"])
def test_main_requires_existing_env_file(tmp_path: Path, command: str) -> None:
    env_file = tmp_path / ".missing-env"
    hash_file = tmp_path / ".env.sha256"

    argv = [command, "--env-file", str(env_file)]
    if command != "check":
        argv.extend(["--hash-file", str(hash_file)])

    exit_code = check_env.main(argv)
    assert exit_code == check_env.EXIT_RUNTIME_ERROR


def test_record_and_verify_detects_mismatched_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    hash_file = tmp_path / ".env.sha256"

    _clear_required_env(monkeypatch)
    _write_env(
        env_file,
        GOOGLE_CLIENT_ID="abc",
        GOOGLE_CLIENT_SECRET="secret",
        GOOGLE_REDIRECT_URI="https://example.com/oauth/callback",
        ANALYSIS_QUEUE_URL="https://sqs.aws.amazon.com/123/queue",
        DYNAMODB_TABLE_NAME="table-name",
        GEMINI_API_KEY="gemini-key",
    )

    exit_code = check_env.main(
        [
            "record",
            "--env-file",
            str(env_file),
            "--hash-file",
            str(hash_file),
        ]
    )
    assert exit_code == check_env.EXIT_OK
    baseline = hash_file.read_text(encoding="utf-8").strip()
    assert baseline

    _clear_required_env(monkeypatch)
    exit_code = check_env.main(
        [
            "verify",
            "--env-file",
            str(env_file),
            "--hash-file",
            str(hash_file),
        ]
    )
    assert exit_code == check_env.EXIT_OK

    _write_env(
        env_file,
        GOOGLE_CLIENT_ID="abc",
        GOOGLE_CLIENT_SECRET="different",
        GOOGLE_REDIRECT_URI="https://example.com/oauth/callback",
        ANALYSIS_QUEUE_URL="https://sqs.aws.amazon.com/123/queue",
        DYNAMODB_TABLE_NAME="table-name",
        GEMINI_API_KEY="gemini-key",
    )

    _clear_required_env(monkeypatch)
    exit_code = check_env.main(
        [
            "verify",
            "--env-file",
            str(env_file),
            "--hash-file",
            str(hash_file),
        ]
    )
    assert exit_code == check_env.EXIT_CHECKSUM_ERROR


def test_validation_failure_for_missing_required_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    hash_file = tmp_path / ".env.sha256"

    _clear_required_env(monkeypatch)
    _write_env(
        env_file,
        GOOGLE_CLIENT_ID="abc",
        GOOGLE_REDIRECT_URI="https://example.com/oauth/callback",
        ANALYSIS_QUEUE_URL="https://sqs.aws.amazon.com/123/queue",
        DYNAMODB_TABLE_NAME="table-name",
        GEMINI_API_KEY="gemini-key",
    )

    exit_code = check_env.main(
        [
            "record",
            "--env-file",
            str(env_file),
            "--hash-file",
            str(hash_file),
        ]
    )
    assert exit_code == check_env.EXIT_VALIDATION_ERROR
