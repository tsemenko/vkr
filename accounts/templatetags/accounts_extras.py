from django import template

from accounts.models import SYSTEM_SECTION_LABELS, WEB_ROLE_LABELS, WEB_ROLE_OPERATOR, WEB_ROLE_SUPER_ADMIN

register = template.Library()


@register.filter
def has_group(user, group_name: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=group_name).exists()


@register.filter
def role_label(group_or_name) -> str:
    name = getattr(group_or_name, "name", group_or_name)
    if not name:
        return ""
    if hasattr(group_or_name, "web_role"):
        return group_or_name.web_role.display_name
    return WEB_ROLE_LABELS.get(name, name)


@register.filter
def section_label(section: str) -> str:
    return SYSTEM_SECTION_LABELS.get(section, section)


@register.filter
def role_section_labels(role) -> str:
    if not role:
        return ""
    labels = role.allowed_section_labels()
    return ", ".join(labels) if labels else "нет"


@register.filter
def role_branch_labels(role) -> str:
    if not role:
        return ""
    labels = role.allowed_branch_labels()
    return ", ".join(labels) if labels else "все филиалы"


@register.filter
def has_section(user, section: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or user.groups.filter(name=WEB_ROLE_SUPER_ADMIN).exists():
        return True
    for group in user.groups.all():
        role = getattr(group, "web_role", None)
        if role and section in (role.allowed_sections or []):
            return True
        if group.name == WEB_ROLE_OPERATOR and section in {"monitoring", "create_user", "logs"}:
            return True
    return False


@register.filter
def can_manage_system(user) -> bool:
    return any(has_section(user, section) for section in ["branches", "groups", "rules", "roles", "users"])


@register.filter
def user_web_role_labels(user) -> str:
    if not user:
        return "нет"
    if getattr(user, "is_superuser", False):
        return "Супер-админ"
    labels = []
    for group in user.groups.all():
        role = getattr(group, "web_role", None)
        if role:
            labels.append(role.display_name)
    return ", ".join(labels) if labels else "нет"


@register.filter
def user_has_web_role(user, role) -> bool:
    if not user or not role:
        return False
    if getattr(user, "is_superuser", False) and getattr(role, "group", None) and role.group.name == WEB_ROLE_SUPER_ADMIN:
        return True
    role_group_id = getattr(getattr(role, "group", None), "id", None)
    if role_group_id is None:
        return False
    return any(group.id == role_group_id for group in user.groups.all())
