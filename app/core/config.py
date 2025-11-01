"""
Application configuration models and helpers.

Centralizes settings management so both the FastAPI app and the asynchronous
analysis agent can share a consistent configuration surface.
"""

from functools import lru_cache
from typing import Optional

from pydantic import BaseSettings, Field, HttpUrl, validator


class GoogleSettings(BaseSettings):
    """Configuration required for interacting with Google APIs."""

    client_id: str = Field(..., alias="GOOGLE_CLIENT_ID")
    client_secret: str = Field(..., alias="GOOGLE_CLIENT_SECRET")
    redirect_uri: HttpUrl = Field(..., alias="GOOGLE_REDIRECT_URI")
    drive_root_folder_id: Optional[str] = Field(
        None,
        alias="GOOGLE_DRIVE_ROOT_FOLDER_ID",
        description="Optional target folder to contain uploaded assets.",
    )


class AWSSettings(BaseSettings):
    """Settings for AWS services used by the platform."""

    region_name: str = Field("us-east-1", alias="AWS_REGION")
    sqs_queue_url: str = Field(..., alias="ANALYSIS_QUEUE_URL")
    analysis_lambda_arn: Optional[str] = Field(
        None,
        alias="ANALYSIS_LAMBDA_ARN",
        description="Optional ARN used for tracing or warm invocations.",
    )
    dynamodb_table_name: str = Field(..., alias="DYNAMODB_TABLE_NAME")
    eventbridge_bus_name: Optional[str] = Field(
        None,
        alias="EVENTBRIDGE_BUS_NAME",
        description="Custom bus for proactive analyses. Defaults to default bus when omitted.",
    )


class GeminiSettings(BaseSettings):
    """Configuration for Gemini model access."""

    api_key: str = Field(..., alias="GEMINI_API_KEY")
    model_name: str = Field("gemini-1.5-pro", alias="GEMINI_MODEL_NAME")
    vision_model_name: str = Field(
        "gemini-1.5-flash", alias="GEMINI_VISION_MODEL_NAME"
    )


class OAuthSettings(BaseSettings):
    """OAuth flow configuration."""

    state_ttl_seconds: int = Field(900, alias="OAUTH_STATE_TTL")
    scopes: tuple[str, ...] = Field(
        (
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/userinfo.email",
            "openid",
        ),
        alias="OAUTH_SCOPES",
    )

    @validator("scopes", pre=True)
    def _split_scopes(cls, value: str | tuple[str, ...]) -> tuple[str, ...]:
        """Support providing scopes as a comma-separated string."""
        if isinstance(value, tuple):
            return value
        return tuple(scope.strip() for scope in value.split(",") if scope.strip())


class AppSettings(BaseSettings):
    """Root settings object for the FastAPI application."""

    environment: str = Field("development", alias="APP_ENV")
    log_level: str = Field("INFO", alias="APP_LOG_LEVEL")
    frontend_base_url: Optional[HttpUrl] = Field(
        None,
        alias="FRONTEND_BASE_URL",
        description="Optional URL for redirecting users back to the front-end.",
    )
    oauth: OAuthSettings = OAuthSettings()
    google: GoogleSettings = GoogleSettings()
    aws: AWSSettings = AWSSettings()
    gemini: GeminiSettings = GeminiSettings()


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
