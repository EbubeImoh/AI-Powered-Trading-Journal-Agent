"""
Application configuration models and helpers.

Centralizes settings management so both the FastAPI app and the asynchronous
analysis agent can share a consistent configuration surface.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

import os

from pydantic import AnyHttpUrl, BaseSettings, Field, HttpUrl, validator


def _load_env_file(path: str = ".env") -> None:
    """Best-effort load key=value pairs from a .env file without extra deps."""
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key or key in os.environ:
            continue
        cleaned = value.strip().strip('"').strip("'")
        os.environ[key] = cleaned


_load_env_file()


class GoogleSettings(BaseSettings):
    """Configuration required for interacting with Google APIs."""

    client_id: str = Field(..., env="GOOGLE_CLIENT_ID")
    client_secret: str = Field(..., env="GOOGLE_CLIENT_SECRET")
    redirect_uri: AnyHttpUrl = Field(..., env="GOOGLE_REDIRECT_URI")
    drive_root_folder_id: Optional[str] = Field(
        None,
        env="GOOGLE_DRIVE_ROOT_FOLDER_ID",
        description="Optional target folder to contain uploaded assets.",
    )


class AWSSettings(BaseSettings):
    """Settings for AWS services used by the platform."""

    region_name: str = Field("us-east-1", env="AWS_REGION")
    sqs_queue_url: str = Field(..., env="ANALYSIS_QUEUE_URL")
    analysis_lambda_arn: Optional[str] = Field(
        None,
        env="ANALYSIS_LAMBDA_ARN",
        description="Optional ARN used for tracing or warm invocations.",
    )
    dynamodb_table_name: str = Field(..., env="DYNAMODB_TABLE_NAME")
    eventbridge_bus_name: Optional[str] = Field(
        None,
        env="EVENTBRIDGE_BUS_NAME",
        description=(
            "Custom bus for proactive analyses. Defaults to default bus when omitted."
        ),
    )


class SecuritySettings(BaseSettings):
    """Security-related configuration."""

    token_encryption_secret: Optional[str] = Field(
        None,
        env="TOKEN_ENCRYPTION_SECRET",
        description=(
            "Secret used to derive the symmetric key for encrypting stored tokens."
        ),
    )


class GeminiSettings(BaseSettings):
    """Configuration for Gemini model access."""

    api_key: str = Field(..., env="GEMINI_API_KEY")
    model_name: str = Field("gemini-1.5-pro", env="GEMINI_MODEL_NAME")
    vision_model_name: str = Field("gemini-1.5-flash", env="GEMINI_VISION_MODEL_NAME")


class OAuthSettings(BaseSettings):
    """OAuth flow configuration."""

    state_ttl_seconds: int = Field(900, env="OAUTH_STATE_TTL")
    scopes: tuple[str, ...] = Field(
        (
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/userinfo.email",
            "openid",
        ),
        env="OAUTH_SCOPES",
    )

    @validator("scopes", pre=True)
    def _split_scopes(
        cls, value: str | tuple[str, ...] | list[str]
    ) -> tuple[str, ...]:
        """Support providing scopes as a comma-separated string."""
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(value)
        return tuple(scope.strip() for scope in value.split(",") if scope.strip())

    class Config:
        env_json_loads = staticmethod(lambda v: v)


class AppSettings(BaseSettings):
    """Root settings object for the FastAPI application."""

    environment: str = Field("development", env="APP_ENV")
    log_level: str = Field("INFO", env="APP_LOG_LEVEL")
    frontend_base_url: Optional[HttpUrl] = Field(
        None,
        env="FRONTEND_BASE_URL",
        description="Optional URL for redirecting users back to the front-end.",
    )
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    oauth: OAuthSettings = Field(default_factory=OAuthSettings)
    google: GoogleSettings = Field(default_factory=GoogleSettings)
    aws: AWSSettings = Field(default_factory=AWSSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    serpapi_api_key: Optional[str] = Field(
        None,
        env="SERPAPI_API_KEY",
        description="Optional SerpAPI key used for web research integration.",
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> AppSettings:
    """Return a cached settings object."""
    return AppSettings()  # type: ignore[call-arg]


__all__ = [
    "AppSettings",
    "AWSSettings",
    "GeminiSettings",
    "GoogleSettings",
    "OAuthSettings",
    "get_settings",
]
