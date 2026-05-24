from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from accounts.models import WEB_ROLE_NAMES, WebUserPasswordState
from accounts.passwords import generate_temporary_password


class Command(BaseCommand):
    help = "Создает или обновляет пользователя веб-интерфейса с временным локальным паролем"

    def add_arguments(self, parser):
        parser.add_argument("username", help="Логин пользователя. Должен совпадать с sAMAccountName в AD")
        parser.add_argument("--first-name", default="", dest="first_name", help="Имя")
        parser.add_argument("--last-name", default="", dest="last_name", help="Фамилия")
        parser.add_argument("--password", default="", help="Временный пароль. Если не указан, будет сгенерирован автоматически")
        parser.add_argument(
            "--groups",
            default="",
            help='Список Django-групп через запятую: "AD Operators" или "AD Super Admins"',
        )
        parser.add_argument(
            "--superuser",
            action="store_true",
            default=False,
            help="Поставить is_superuser=True",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"].strip()
        if not username:
            raise CommandError("username не может быть пустым")

        user, created = User.objects.get_or_create(username=username)
        user.first_name = options["first_name"].strip()
        user.last_name = options["last_name"].strip()
        user.is_active = True
        user.is_staff = False
        user.is_superuser = options["superuser"]
        temporary_password = options["password"].strip() or generate_temporary_password()
        user.set_password(temporary_password)
        user.save()
        WebUserPasswordState.objects.update_or_create(
            user=user,
            defaults={"must_change_password": True},
        )

        groups_raw = options["groups"].strip()
        if groups_raw:
            group_names = [name.strip() for name in groups_raw.split(",") if name.strip()]
            forbidden = [name for name in group_names if name not in WEB_ROLE_NAMES]
            if forbidden:
                raise CommandError("Разрешены только роли: " + ", ".join(WEB_ROLE_NAMES))
            groups = []
            missing = []
            for name in group_names:
                try:
                    groups.append(Group.objects.get(name=name))
                except Group.DoesNotExist:
                    missing.append(name)
            if missing:
                raise CommandError(
                    "Не найдены Django-группы: " + ", ".join(missing) + ". Сначала запусти bootstrap_web_roles."
                )
            user.groups.set(groups)

        action = "Создан" if created else "Обновлён"
        group_list = ", ".join(user.groups.values_list("name", flat=True)) or "без групп"
        self.stdout.write(self.style.SUCCESS(
            f"{action} пользователь {user.username}; is_superuser={user.is_superuser}; группы: {group_list}; временный пароль: {temporary_password}"
        ))
