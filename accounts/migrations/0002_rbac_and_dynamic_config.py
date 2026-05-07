from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AdManagedGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=256)),
                ("dn", models.CharField(blank=True, default="", max_length=512)),
                ("is_active", models.BooleanField(default=True)),
                ("managed_by_sync", models.BooleanField(default=False)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Branch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.SlugField(max_length=32, unique=True)),
                ("label", models.CharField(max_length=128)),
                ("ou_dn", models.CharField(max_length=512)),
                ("is_hq", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=100)),
                ("ad_ou_dn", models.CharField(blank=True, default="", max_length=512)),
                ("last_synced_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["sort_order", "label"]},
        ),
        migrations.CreateModel(
            name="WebGroupRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_system", models.BooleanField(default=False)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                (
                    "group",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="web_role", to="auth.group"),
                ),
            ],
            options={"ordering": ["group__name"]},
        ),
        migrations.CreateModel(
            name="DefaultAssignmentRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("applies_to_gender", models.CharField(blank=True, default="", max_length=1)),
                (
                    "source",
                    models.CharField(
                        choices=[("local", "Локально"), ("ad", "Из AD")],
                        default="local",
                        max_length=16,
                    ),
                ),
                ("priority", models.IntegerField(default=100)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "branch",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="default_rules", to="accounts.branch"),
                ),
                (
                    "group",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="default_rules", to="accounts.admanagedgroup"),
                ),
            ],
            options={"ordering": ["priority", "id"]},
        ),
        migrations.CreateModel(
            name="AdSyncMapping",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ad_group_dn", models.CharField(max_length=512, unique=True)),
                ("ad_group_name", models.CharField(max_length=256)),
                ("is_active", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                (
                    "local_group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ad_mappings",
                        to="accounts.admanagedgroup",
                    ),
                ),
            ],
            options={"ordering": ["ad_group_name"]},
        ),
        migrations.AddConstraint(
            model_name="defaultassignmentrule",
            constraint=models.UniqueConstraint(
                fields=("branch", "applies_to_gender", "group"),
                name="uniq_default_rule_branch_gender_group",
            ),
        ),
    ]
