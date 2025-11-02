"""
Factory functions to provide shared clients and services as FastAPI dependencies.
"""

from functools import lru_cache

from app.clients import (
    GeminiClient,
    GoogleDriveClient,
    GoogleOAuthClient,
    GoogleSheetsClient,
    OAuthStateEncoder,
    SQLiteQueueClient,
    SQLiteStore,
    WebSearchClient,
)
from app.core.config import get_settings
from app.services import (
    AnalysisQueueService,
    GoogleTokenService,
    TokenCipherService,
    TradeCaptureStore,
    TradeExtractionService,
    TradeIngestionService,
)


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
    return GoogleDriveClient(
        token_service=get_google_token_service(),
        drive_root_folder_id=settings.google.drive_root_folder_id,
    )


@lru_cache()
def get_sheets_client() -> GoogleSheetsClient:
    """Provide Google Sheets client instance."""
    return GoogleSheetsClient(get_google_token_service())


@lru_cache()
@lru_cache()
def get_sqlite_store() -> SQLiteStore:
    """Provide shared SQLite record store."""
    settings = _settings()
    return SQLiteStore(settings.trade_capture_db_path)


@lru_cache()
def get_queue_client() -> SQLiteQueueClient:
    """Provide SQLite-backed queue client."""
    settings = _settings()
    return SQLiteQueueClient(settings.trade_capture_db_path)


@lru_cache()
def get_google_token_service() -> GoogleTokenService:
    """Provide helper for managing Google OAuth tokens."""
    settings = _settings()
    return GoogleTokenService(
        store=get_sqlite_store(),
        oauth_client=get_google_oauth_client(),
        google_settings=settings.google,
        oauth_settings=settings.oauth,
        token_cipher=get_token_cipher_service(),
    )


@lru_cache()
def get_token_cipher_service() -> TokenCipherService:
    """Provide symmetric encryption helper for token storage."""
    settings = _settings()
    secret = settings.security.token_encryption_secret or settings.google.client_secret
    return TokenCipherService(secret=secret)


@lru_cache()
def get_gemini_client() -> GeminiClient:
    """Provide Gemini client instance."""
    settings = _settings()
    return GeminiClient(settings.gemini)


@lru_cache()
def get_web_search_client() -> WebSearchClient | None:
    """Provide web search client when SerpAPI is configured."""
    settings = _settings()
    api_key = settings.serpapi_api_key
    if not api_key:
        return None
    return WebSearchClient(api_key=api_key)


def get_trade_extraction_service() -> TradeExtractionService:
    """Build a trade extraction service using Gemini."""
    return TradeExtractionService(get_gemini_client())


def get_trade_ingestion_service() -> TradeIngestionService:
    """Build a trade ingestion service using configured clients."""
    return TradeIngestionService(
        drive_client=get_drive_client(),
        sheets_client=get_sheets_client(),
    )


def get_analysis_queue_service() -> AnalysisQueueService:
    """Build an analysis queue service."""
    return AnalysisQueueService(
        queue_client=get_queue_client(),
        store=get_sqlite_store(),
    )


@lru_cache()
def get_trade_capture_store() -> TradeCaptureStore:
    """Provide a process-local trade capture store."""
    settings = _settings()
    return TradeCaptureStore(
        db_path=settings.trade_capture_db_path,
    )


__all__ = [
    "get_analysis_queue_service",
    "get_drive_client",
    "get_gemini_client",
    "get_google_oauth_client",
    "get_token_cipher_service",
    "get_google_token_service",
    "get_oauth_state_encoder",
    "get_web_search_client",
    "get_sheets_client",
    "get_trade_extraction_service",
    "get_trade_ingestion_service",
    "get_trade_capture_store",
    "get_sqlite_store",
    "get_queue_client",
]
