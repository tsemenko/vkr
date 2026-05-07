from __future__ import annotations

from celery import shared_task

from .services.monitoring import refresh_snapshot


@shared_task(ignore_result=True, autoretry_for=(Exception,), retry_backoff=5, retry_kwargs={"max_retries": 3})
def refresh_ad_monitoring_snapshot() -> None:
    refresh_snapshot()
