from django.db import migrations


LEGACY_MODELS = ("adgroup", "organizationalunit", "branchdirectory", "settingschangelog")
LEGACY_TABLES = (
    "accounts_adgroup",
    "accounts_organizationalunit",
    "accounts_branchdirectory",
    "accounts_settingschangelog",
)


def cleanup_legacy_contenttypes(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    stale_cts = ContentType.objects.filter(app_label="accounts", model__in=LEGACY_MODELS)
    Permission.objects.filter(content_type__in=stale_cts).delete()
    stale_cts.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("accounts", "0003_seed_branches_and_roles"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[f"DROP TABLE IF EXISTS {table};" for table in LEGACY_TABLES],
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunPython(cleanup_legacy_contenttypes, migrations.RunPython.noop),
    ]
