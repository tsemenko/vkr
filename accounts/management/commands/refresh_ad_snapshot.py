from __future__ import annotations

from django.core.management.base import BaseCommand

from accounts.services.monitoring import refresh_snapshot


class Command(BaseCommand):
    help = 'Принудительно обновляет snapshot мониторинга AD и сохраняет его в кэш.'

    def handle(self, *args, **options):
        snapshot = refresh_snapshot()
        self.stdout.write(self.style.SUCCESS(
            'Snapshot обновлён. '
            f"Пароли: {snapshot['stats']['expiry_total']}, "
            f"неактивные: {snapshot['stats']['inactive_total']}, "
            f"заблокированные: {snapshot['stats']['blocked_total']}"
        ))
