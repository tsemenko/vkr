from django.core.management.base import BaseCommand

from accounts.services.directory import bootstrap_directory_from_settings


class Command(BaseCommand):
    help = "Заполняет филиалы, AD-группы, правила по умолчанию и базовые роли из settings/.env"

    def handle(self, *args, **options):
        result = bootstrap_directory_from_settings()
        self.stdout.write(
            self.style.SUCCESS(
                "Данные справочников обновлены: "
                f"филиалы={result['branches']}, "
                f"AD-группы={result['groups']}, "
                f"правила={result['rules']}, "
                f"роли={result['roles']}"
            )
        )
