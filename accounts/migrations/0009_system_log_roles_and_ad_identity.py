from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


SYSTEM_ACTIONS = {
    "system_create_branch": "Добавление филиала",
    "system_create_ad_group": "Добавление AD-группы",
    "system_create_rule": "Добавление правила",
    "system_update_web_access": "Назначение роли",
    "system_create_web_user": "Создание пользователя веб-сервиса",
    "system_delete_web_user": "Удаление пользователя веб-сервиса",
    "system_upsert_role": "Изменение роли",
}


def migrate_system_events(apps, schema_editor):
    ActionLog = apps.get_model("accounts", "ActionLog")
    SystemLog = apps.get_model("accounts", "SystemLog")
    for item in ActionLog.objects.filter(action__startswith="system_").order_by("created_at"):
        SystemLog.objects.get_or_create(
            created_at=item.created_at,
            actor_id=item.actor_id,
            action=item.action,
            target=item.target_login,
            success=item.success,
            details=item.details,
        )


def cleanup_roles_and_group_identities(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    WebGroupRole = apps.get_model("accounts", "WebGroupRole")
    AdManagedGroup = apps.get_model("accounts", "AdManagedGroup")

    WebGroupRole.objects.filter(group__name="AD Admins").delete()
    Group.objects.filter(name="AD Admins").delete()

    role_descriptions = {
        "AD Super Admins": "Супер-администратор управляет справочниками, ролями, пользователями веб-сервиса и системным журналом.",
        "AD Operators": "Операторы могут просматривать мониторинг, создавать учетные записи AD и разблокировать пользователей.",
    }
    for group_name, description in role_descriptions.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        WebGroupRole.objects.update_or_create(
            group=group,
            defaults={"is_system": True, "description": description},
        )

    for group in AdManagedGroup.objects.filter(dn=""):
        # Исправляет типовой случай: вручную добавили отображаемое имя «1с»,
        # а в AD у группы используется sAMAccountName «1c».
        if group.code == "1c":
            group.dn = "1c"
        else:
            group.dn = group.name
        group.save(update_fields=["dn"])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("accounts", "0008_fix_hq_branch_label"),
    ]

    operations = [
        migrations.CreateModel(
            name="SystemLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("action", models.CharField(max_length=64)),
                ("target", models.CharField(blank=True, default="", max_length=150)),
                ("success", models.BooleanField(default=True)),
                ("details", models.TextField(blank=True, default="")),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AlterModelOptions(name="actionlog", options={"ordering": ["-created_at"]}),
        migrations.AlterField(
            model_name="defaultassignmentrule",
            name="source",
            field=models.CharField(
                choices=[("local", "Локально"), ("ad", "Из AD")],
                default="ad",
                max_length=16,
            ),
        ),
        migrations.RunPython(migrate_system_events, reverse_noop),
        migrations.RunPython(cleanup_roles_and_group_identities, reverse_noop),
    ]
