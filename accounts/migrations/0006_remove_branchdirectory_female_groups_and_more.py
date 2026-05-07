
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_merge_20260419_1941"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AlterModelOptions(
                    name="actionlog",
                    options={},
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="action",
                    field=models.CharField(max_length=64),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="actor",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="created_at",
                    field=models.DateTimeField(auto_now_add=True),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="details",
                    field=models.TextField(blank=True, default=""),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="success",
                    field=models.BooleanField(default=False),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="target_login",
                    field=models.CharField(blank=True, default="", max_length=128),
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name="branchdirectory",
                    name="female_groups",
                ),
                migrations.RemoveField(
                    model_name="branchdirectory",
                    name="default_groups",
                ),
                migrations.RemoveField(
                    model_name="branchdirectory",
                    name="ou",
                ),
                migrations.RemoveField(
                    model_name="settingschangelog",
                    name="actor",
                ),
                migrations.AlterModelOptions(
                    name="actionlog",
                    options={},
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="action",
                    field=models.CharField(max_length=64),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="actor",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="created_at",
                    field=models.DateTimeField(auto_now_add=True),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="details",
                    field=models.TextField(blank=True, default=""),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="success",
                    field=models.BooleanField(default=False),
                ),
                migrations.AlterField(
                    model_name="actionlog",
                    name="target_login",
                    field=models.CharField(blank=True, default="", max_length=128),
                ),
                migrations.DeleteModel(
                    name="ADGroup",
                ),
                migrations.DeleteModel(
                    name="BranchDirectory",
                ),
                migrations.DeleteModel(
                    name="OrganizationalUnit",
                ),
                migrations.DeleteModel(
                    name="SettingsChangeLog",
                ),
            ],
        ),
    ]
