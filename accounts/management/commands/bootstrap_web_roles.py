from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from accounts.models import WEB_ROLE_NAMES, WebGroupRole
from accounts.services.directory import BASE_WEB_GROUPS


class Command(BaseCommand):
    help = "Создаёт базовые Django-группы для доступа в веб-интерфейс"

    def handle(self, *args, **options):
        WebGroupRole.objects.filter(group__name="AD Admins").delete()
        Group.objects.filter(name="AD Admins").delete()

        created_names = []
        for name in WEB_ROLE_NAMES:
            group, created = Group.objects.get_or_create(name=name)
            WebGroupRole.objects.update_or_create(
                group=group,
                defaults={"description": BASE_WEB_GROUPS.get(name, ""), "is_system": True},
            )
            if created:
                created_names.append(name)

        if created_names:
            self.stdout.write(self.style.SUCCESS("Созданы группы: " + ", ".join(created_names)))
        else:
            self.stdout.write(self.style.WARNING("Базовые группы уже существуют"))
