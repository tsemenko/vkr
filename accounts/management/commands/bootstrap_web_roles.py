from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Создаёт базовые Django-группы для доступа в веб-интерфейс"

    def handle(self, *args, **options):
        created_names = []
        for name in ["AD Admins", "AD Super Admins"]:
            _, created = Group.objects.get_or_create(name=name)
            if created:
                created_names.append(name)

        if created_names:
            self.stdout.write(self.style.SUCCESS(
                "Созданы группы: " + ", ".join(created_names)
            ))
        else:
            self.stdout.write(self.style.WARNING("Все базовые группы уже существуют"))
