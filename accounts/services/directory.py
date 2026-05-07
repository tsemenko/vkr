from __future__ import annotations

import hashlib
import re

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction

from accounts.models import AdManagedGroup, Branch, DefaultAssignmentRule, WebGroupRole

BASE_WEB_GROUPS = {
    "AD Operators": "Операторы могут просматривать мониторинг и создавать учетные записи AD.",
    "AD Admins": "Администраторы могут работать с журналом действий и ошибками.",
    "AD Super Admins": "Суперадминистраторы могут управлять справочниками и доступом.",
}


def _group_code(name: str) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return f"ad_group_{base}_{digest}"[:64] if base else f"ad_group_{digest}"


@transaction.atomic
def bootstrap_directory_from_settings() -> dict:
    result = {"branches": 0, "groups": 0, "rules": 0, "roles": 0}

    for branch_key, label in getattr(settings, "BRANCH_LABELS", {}).items():
        ou_dn = getattr(settings, "OU_MAP", {}).get(branch_key, "")
        if not label or not ou_dn:
            continue
        _, created = Branch.objects.update_or_create(
            key=branch_key,
            defaults={"label": label, "ou_dn": ou_dn, "is_hq": branch_key == "hq", "is_active": True, "sort_order": 1 if branch_key == "hq" else 100},
        )
        if created:
            result["branches"] += 1

    hq_groups = list(getattr(settings, "GROUPS_HQ", []))
    hq_female_groups = list(getattr(settings, "GROUPS_HQ_F", []))
    branch_groups = list(getattr(settings, "GROUPS_BRANCH", []))
    branch_female_groups = list(getattr(settings, "GROUPS_BRANCH_F", []))
    all_groups = sorted(set(hq_groups + hq_female_groups + branch_groups + branch_female_groups))

    group_by_name = {}
    for group_name in all_groups:
        group, created = AdManagedGroup.objects.get_or_create(name=group_name, defaults={"code": _group_code(group_name), "is_active": True})
        group_by_name[group_name] = group
        if created:
            result["groups"] += 1

    for branch in Branch.objects.all():
        base_groups = hq_groups if branch.is_hq else branch_groups
        female_groups = hq_female_groups if branch.is_hq else branch_female_groups
        for priority, group_name in enumerate(base_groups, start=100):
            group = group_by_name.get(group_name)
            if not group:
                continue
            _, created = DefaultAssignmentRule.objects.get_or_create(branch=branch, applies_to_gender="", group=group, defaults={"source": DefaultAssignmentRule.SOURCE_LOCAL, "priority": priority, "is_active": True})
            if created:
                result["rules"] += 1
        for priority, group_name in enumerate(female_groups, start=200):
            group = group_by_name.get(group_name)
            if not group:
                continue
            _, created = DefaultAssignmentRule.objects.get_or_create(branch=branch, applies_to_gender="F", group=group, defaults={"source": DefaultAssignmentRule.SOURCE_LOCAL, "priority": priority, "is_active": True})
            if created:
                result["rules"] += 1

    for group_name, description in BASE_WEB_GROUPS.items():
        group, created = Group.objects.get_or_create(name=group_name)
        WebGroupRole.objects.update_or_create(group=group, defaults={"description": description, "is_system": True})
        if created:
            result["roles"] += 1

    return result
