from django.db import migrations, models


ALL_SECTIONS = ["monitoring", "create_user", "logs", "branches", "groups", "rules", "roles", "users"]
OPERATOR_SECTIONS = ["monitoring", "create_user", "logs"]


def seed_role_sections(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    WebGroupRole = apps.get_model("accounts", "WebGroupRole")

    descriptions = {
        "AD Super Admins": "Супер-администратор управляет всеми разделами веб-сервиса.",
        "AD Operators": "Оператор просматривает мониторинг, создает учетные записи AD и работает с журналом.",
    }
    for group_name, sections in {"AD Super Admins": ALL_SECTIONS, "AD Operators": OPERATOR_SECTIONS}.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        WebGroupRole.objects.update_or_create(
            group=group,
            defaults={"is_system": True, "description": descriptions[group_name], "allowed_sections": sections},
        )


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_system_log_roles_and_ad_identity"),
    ]

    operations = [
        migrations.AddField(
            model_name="webgrouprole",
            name="allowed_sections",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(seed_role_sections, reverse_noop),
    ]
