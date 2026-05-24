from django.db import migrations


def fix_hq_branch_label(apps, schema_editor):
    Branch = apps.get_model("accounts", "Branch")
    Branch.objects.filter(key="hq").update(label="Головной вуз", is_hq=True, sort_order=1)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_remove_ad_sync_tail"),
    ]

    operations = [
        migrations.RunPython(fix_hq_branch_label, noop),
    ]
