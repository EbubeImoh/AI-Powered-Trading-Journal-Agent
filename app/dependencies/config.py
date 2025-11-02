"""
FastAPI dependency utilities for injecting configuration and shared clients.
"""

from functools import lru_cache

from fastapi import Depends

from app.core.config import AppSettings, get_settings


@lru_cache()
def _settings_singleton() -> AppSettings:
    """Ensure configuration is created once per process."""
    return get_settings()


def get_app_settings() -> AppSettings:
    """FastAPI dependency returning application settings."""
    return _settings_singleton()


SettingsDependency = Depends(get_app_settings)

__all__ = ["SettingsDependency", "get_app_settings"]
