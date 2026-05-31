from __future__ import annotations

from api.config import settings


def browser_rendering_enabled() -> bool:
    return (
        settings.SCRAPING_FEATURE_BROWSER_ENABLED
        and settings.SCRAPING_ENABLED
        and settings.SCRAPING_PROXY_LAYER_ENABLED
    )


def proxy_rotation_enabled() -> bool:
    return (
        settings.SCRAPING_FEATURE_PROXY_ENABLED
        and settings.SCRAPING_PROXY_LAYER_ENABLED
        and settings.SCRAPING_ENABLED
        and settings.SCRAPING_PROXY_ROTATION_ENABLED
        and bool(settings.SCRAPING_PROXY_LIST)
    )


def async_queue_enabled() -> bool:
    return (
        settings.SCRAPING_FEATURE_ASYNC_QUEUE_ENABLED
        and settings.SCRAPING_ENABLED
        and settings.SCRAPING_PROXY_LAYER_ENABLED
    )


def cache_fallback_enabled() -> bool:
    return settings.SCRAPING_FEATURE_CACHE_FALLBACK_ENABLED
