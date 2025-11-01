"""Test helper that normalizes sys.path and environment defaults."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


_DEFAULT_ENV_VARS: dict[str, str] = {
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_REDIRECT_URI": "https://example.com/oauth/callback",
    "ANALYSIS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123456789012/analysis",
    "DYNAMODB_TABLE_NAME": "analysis-table",
    "GEMINI_API_KEY": "test-gemini-key",
    "TOKEN_ENCRYPTION_SECRET": "test-secret",
}

for key, value in _DEFAULT_ENV_VARS.items():
    os.environ.setdefault(key, value)
