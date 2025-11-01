"""
Factory functions to provide shared clients and services as FastAPI dependencies.
"""
from functools import lru_cache

from app.clients import (
    DynamoDBClient,
    GoogleDriveClient,
    GoogleOAuthClient,
    GoogleSheetsClient,
    OAuthStateEncoder,
    SQSClient,
)
from app.core.config import get_settings
from app.services import AnalysisQueueService, TradeIngestionService


@lru_cache()
def _settings():
    """Internal helper to cache settings for client factories."""
    return get_settings()


@lru_cache()
def get_oauth_state_encoder() -> OAuthStateEncoder:
    """Provide an OAuth state encoder derived from the Google client secret."""
    settings = _settings()
    return OAuthStateEncoder(secret_key=settings.google.client_secret)


@lru_cache()
def get_google_oauth_client() -> GoogleOAuthClient:
    """Create a singleton Google OAuth client."""
    settings = _settings()
    return GoogleOAuthClient(settings.google, settings.oauth)


@lru_cache()
def get_drive_client() -> GoogleDriveClient:
    """Provide Google Drive client instance."""
    settings = _settings()
    return GoogleDriveClient(settings.google)


@lru_cache()
def get_sheets_client() -> GoogleSheetsClient:
    """Provide Google Sheets client instance."""
    settings = _settings()
    return GoogleSheetsClient(settings.google)


@lru_cache()
def get_sqs_client() -> SQSClient:
    """Provide SQS client for queueing analysis jobs."""
    settings = _settings()
    return SQSClient(settings.aws)


@lru_cache()
def get_dynamodb_client() -> DynamoDBClient:
    """Provide DynamoDB client for persistence."""
    settings = _settings()
    return DynamoDBClient(settings.aws)


def get_trade_ingestion_service() -> TradeIngestionService:
    """Build a trade ingestion service using configured clients."""
    return TradeIngestionService(
        drive_client=get_drive_client(),
        sheets_client=get_sheets_client(),
    )


def get_analysis_queue_service() -> AnalysisQueueService:
    """Build an analysis queue service."""
    return AnalysisQueueService(
        sqs_client=get_sqs_client(),
        dynamodb_client=get_dynamodb_client(),
    )


__all__ = [
    "get_analysis_queue_service",
    "get_dynamodb_client",
    "get_drive_client",
    "get_google_oauth_client",
    "get_oauth_state_encoder",
    "get_sheets_client",
    "get_trade_ingestion_service",
]
