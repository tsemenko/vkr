from django.conf import settings
from django.db import migrations


DEFAULT_ORDER = ["hq", "sposad", "penza", "ryazan", "rostov", "nnov"]


def seed_branches(apps, schema_editor):
    Branch = apps.get_model("accounts", "Branch")
    labels = getattr(settings, "BRANCH_LABELS", {}) or {}
    ou_map = getattr(settings, "OU_MAP", {}) or {}

    keys = list(DEFAULT_ORDER)
    for key in labels.keys():
        if key not in keys:
            keys.append(key)

    for idx, key in enumerate(keys):
        label = labels.get(key) or key
        ou_dn = ou_map.get(key) or ""
        Branch.objects.get_or_create(
            key=key,
            defaults={
                "label": label,
                "ou_dn": ou_dn,
                "ad_ou_dn": ou_dn,
                "is_hq": key == "hq",
                "is_active": True,
                "sort_order": idx,
            },
        )


def seed_web_super_admin_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    WebGroupRole = apps.get_model("accounts", "WebGroupRole")

    group, _ = Group.objects.get_or_create(name="AD Super Admins")
    WebGroupRole.objects.get_or_create(
        group=group,
        defaults={
            "is_system": True,
            "description": "Системная роль супер-админа веб-интерфейса",
        },
    )


def seed_default_assignment_rules(apps, schema_editor):
    Branch = apps.get_model("accounts", "Branch")
    AdManagedGroup = apps.get_model("accounts", "AdManagedGroup")
    DefaultAssignmentRule = apps.get_model("accounts", "DefaultAssignmentRule")

    group_sets = {
        ("hq", ""): getattr(settings, "GROUPS_HQ", []) or [],
        ("hq", "F"): getattr(settings, "GROUPS_HQ_F", []) or [],
        ("branch", ""): getattr(settings, "GROUPS_BRANCH", []) or [],
        ("branch", "F"): getattr(settings, "GROUPS_BRANCH_F", []) or [],
    }

    for branch in Branch.objects.filter(is_active=True):
        branch_kind = "hq" if branch.is_hq else "branch"
        for gender in ("", "F"):
            names = group_sets.get((branch_kind, gender), [])
            for idx, name in enumerate(names):
                code = name.lower().replace(" ", "-")
                managed_group, _ = AdManagedGroup.objects.get_or_create(
                    code=code[:64],
                    defaults={"name": name, "dn": "", "is_active": True},
                )
                DefaultAssignmentRule.objects.get_or_create(
                    branch=branch,
                    applies_to_gender=gender,
                    group=managed_group,
                    defaults={"source": "local", "priority": idx, "is_active": True},
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_rbac_and_dynamic_config"),
    ]

    operations = [
        migrations.RunPython(seed_branches, noop),
        migrations.RunPython(seed_web_super_admin_group, noop),
        migrations.RunPython(seed_default_assignment_rules, noop),
    ]
