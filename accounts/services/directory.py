from __future__ import annotations

import hashlib
import re

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction

from accounts.models import (
    AdManagedGroup,
    Branch,
    DefaultAssignmentRule,
    WEB_ROLE_OPERATOR,
    WEB_ROLE_SUPER_ADMIN,
    WebGroupRole,
)

BASE_WEB_GROUPS = {
    WEB_ROLE_OPERATOR: "Операторы могут просматривать мониторинг, создавать учетные записи AD и разблокировать пользователей.",
    WEB_ROLE_SUPER_ADMIN: "Супер-администратор управляет справочниками, ролями, пользователями веб-сервиса и системным журналом.",
}


_DISABLED_WEB_GROUPS = {"AD Admins"}


def _group_code(name: str) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return f"ad_group_{base}_{digest}"[:64] if base else f"ad_group_{digest}"


@transaction.atomic
def bootstrap_directory_from_settings() -> dict:
    result = {"branches": 0, "groups": 0, "rules": 0, "roles": 0, "removed_roles": 0}

    for branch_key, label in getattr(settings, "BRANCH_LABELS", {}).items():
        ou_dn = getattr(settings, "OU_MAP", {}).get(branch_key, "")
        if not label or not ou_dn:
            continue
        _, created = Branch.objects.update_or_create(
            key=branch_key,
            defaults={
                "label": label,
                "ou_dn": ou_dn,
                "is_hq": branch_key == "hq",
                "is_active": True,
                "sort_order": 1 if branch_key == "hq" else 100,
            },
        )
        if created:
            result["branches"] += 1

    hq_groups = list(getattr(settings, "GROUPS_HQ", []))
    branch_groups = list(getattr(settings, "GROUPS_BRANCH", []))
    all_groups = sorted(set(hq_groups + branch_groups))

    group_by_name = {}
    for group_name in all_groups:
        group, created = AdManagedGroup.objects.get_or_create(
            name=group_name,
            defaults={"code": _group_code(group_name), "dn": group_name, "is_active": True},
        )
        if not group.dn:
            group.dn = group_name
            group.save(update_fields=["dn"])
        group_by_name[group_name] = group
        if created:
            result["groups"] += 1

    for branch in Branch.objects.all():
        base_groups = hq_groups if branch.is_hq else branch_groups
        for priority, group_name in enumerate(base_groups, start=100):
            group = group_by_name.get(group_name)
            if not group:
                continue
            _, created = DefaultAssignmentRule.objects.get_or_create(
                branch=branch,
                applies_to_gender="",
                group=group,
                defaults={"source": DefaultAssignmentRule.SOURCE_AD, "priority": priority, "is_active": True},
            )
            if created:
                result["rules"] += 1

    WebGroupRole.objects.filter(group__name__in=_DISABLED_WEB_GROUPS).delete()
    deleted, _ = Group.objects.filter(name__in=_DISABLED_WEB_GROUPS).delete()
    result["removed_roles"] += deleted

    for group_name, description in BASE_WEB_GROUPS.items():
        group, created = Group.objects.get_or_create(name=group_name)
        WebGroupRole.objects.update_or_create(group=group, defaults={"description": description, "is_system": True})
        if created:
            result["roles"] += 1

    return result
