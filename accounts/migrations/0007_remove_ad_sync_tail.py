from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_remove_branchdirectory_female_groups_and_more"),
    ]

    operations = [
        migrations.RemoveField(model_name="branch", name="ad_ou_dn"),
        migrations.RemoveField(model_name="branch", name="last_synced_at"),
        migrations.RemoveField(model_name="admanagedgroup", name="managed_by_sync"),
        migrations.RemoveField(model_name="admanagedgroup", name="last_synced_at"),
        migrations.DeleteModel(name="AdSyncMapping"),
    ]
