from __future__ import annotations

import time
from copy import deepcopy

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .ad_logic import get_ad_analytics_snapshot


def _cache_key() -> str:
    return settings.MONITORING_CACHE_KEY


def _cache_backend_name() -> str:
    return cache.__class__.__name__


def empty_snapshot(status: str = 'warming_up', error: str = '') -> dict:
    return {
        'stats': {
            'expiry_total': 0,
            'inactive_30_total': 0,
            'inactive_60_total': 0,
            'inactive_90_total': 0,
            'inactive_total': 0,
            'blocked_total': 0,
        },
        'expiry_users': [],
        'inactive_30': [],
        'inactive_60': [],
        'inactive_90': [],
        'blocked_users': [],
        'meta': {
            'scanned_users': 0,
            'search_base': getattr(settings, 'AD_USERS_SEARCH_BASE', '') or '',
        },
        'monitoring_status': status,
        'monitoring_error': error,
        'monitoring_updated_at': '',
        'monitoring_generated_in_ms': 0,
        'monitoring_cache_backend': _cache_backend_name(),
        'monitoring_source': 'empty',
        'monitoring_poll_seconds': settings.MONITORING_FRAGMENT_POLL_SECONDS,
    }


def build_snapshot() -> dict:
    started = time.perf_counter()
    snapshot = get_ad_analytics_snapshot(max_days=settings.AD_ANALYTICS_MAX_DAYS)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    updated_at = timezone.localtime(timezone.now())

    snapshot.update({
        'monitoring_status': 'ok',
        'monitoring_error': '',
        'monitoring_updated_at': updated_at.strftime('%d.%m.%Y %H:%M:%S'),
        'monitoring_generated_in_ms': elapsed_ms,
        'monitoring_cache_backend': _cache_backend_name(),
        'monitoring_source': 'live',
        'monitoring_poll_seconds': settings.MONITORING_FRAGMENT_POLL_SECONDS,
    })
    return snapshot


def save_snapshot(snapshot: dict) -> dict:
    cache.set(_cache_key(), deepcopy(snapshot), settings.MONITORING_CACHE_TIMEOUT)
    return snapshot


def refresh_snapshot() -> dict:
    return save_snapshot(build_snapshot())


def get_cached_snapshot() -> dict | None:
    snapshot = cache.get(_cache_key())
    if not snapshot:
        return None
    snapshot = deepcopy(snapshot)
    snapshot['monitoring_source'] = 'cache'
    snapshot['monitoring_cache_backend'] = _cache_backend_name()
    snapshot['monitoring_poll_seconds'] = settings.MONITORING_FRAGMENT_POLL_SECONDS
    return snapshot


def get_or_build_snapshot() -> dict:
    snapshot = get_cached_snapshot()
    if snapshot is not None:
        return snapshot
    if settings.MONITORING_FORCE_SYNC_ON_MISS:
        return refresh_snapshot()
    return empty_snapshot(status='warming_up')


def trigger_async_refresh() -> bool:
    try:
        from accounts.tasks import refresh_ad_monitoring_snapshot

        refresh_ad_monitoring_snapshot.delay()
        return True
    except Exception:
        return False
