from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Создаёт или обновляет Django-пользователя под LDAP-логин без локального пароля"

    def add_arguments(self, parser):
        parser.add_argument("username", help="Логин пользователя. Должен совпадать с sAMAccountName в AD")
        parser.add_argument("--first-name", default="", dest="first_name", help="Имя")
        parser.add_argument("--last-name", default="", dest="last_name", help="Фамилия")
        parser.add_argument("--email", default="", help="Email")
        parser.add_argument(
            "--groups",
            default="",
            help='Список Django-групп через запятую, например "AD Operators,AD Admins"',
        )
        parser.add_argument(
            "--active",
            action="store_true",
            default=False,
            help="Сделать пользователя активным",
        )
        parser.add_argument(
            "--staff",
            action="store_true",
            default=False,
            help="Поставить is_staff=True",
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
        user.email = options["email"].strip()
        user.is_active = True if options["active"] else user.is_active or True
        user.is_staff = options["staff"]
        user.is_superuser = options["superuser"]
        user.set_unusable_password()
        user.save()

        groups_raw = options["groups"].strip()
        if groups_raw:
            group_names = [name.strip() for name in groups_raw.split(",") if name.strip()]
            groups = []
            missing = []
            for name in group_names:
                try:
                    groups.append(Group.objects.get(name=name))
                except Group.DoesNotExist:
                    missing.append(name)
            if missing:
                raise CommandError(
                    "Не найдены Django-группы: " + ", ".join(missing) + ". Сначала запусти bootstrap_web_roles или создай их вручную."
                )
            user.groups.set(groups)

        action = "Создан" if created else "Обновлён"
        group_list = ", ".join(user.groups.values_list("name", flat=True)) or "без групп"
        self.stdout.write(self.style.SUCCESS(
            f"{action} пользователь {user.username}; is_active={user.is_active}; is_staff={user.is_staff}; is_superuser={user.is_superuser}; группы: {group_list}; локальный пароль отключён"
        ))
