from __future__ import annotations

import json
from typing import Any

from django.conf import settings

from ..models import Branch, DefaultAssignmentRule
from ..utils import normalize_birth_date, normalize_login_candidates
from .powershell import (
    ps_check_ad_group_exists,
    ps_check_login_candidates,
    ps_check_login_exists,
    ps_check_ou_exists,
    ps_check_upn_exists,
    ps_create_user,
    ps_get_ad_analytics,
    ps_get_blocked_users,
    ps_get_inactive_users,
    ps_unlock_user,
    run_ps,
)


def _require_settings() -> None:
    missing = []
    for k in ("DC_HOST", "DC_WINRM_USER", "DC_WINRM_PASSWORD"):
        if not getattr(settings, k, None):
            missing.append(k)
    if missing:
        raise RuntimeError("Не настроены параметры подключения к DC (WinRM): " + ", ".join(missing))


def _load_json_payload(script: str) -> Any:
    _require_settings()
    code, out, err = run_ps(script)
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"WinRM status={code}")

    payload = (out or "").strip()
    if not payload:
        return []

    try:
        return json.loads(payload)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Некорректный ответ PowerShell: {e}") from e


def _ensure_list(data: Any) -> list[dict]:
    if not data:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise RuntimeError("Некорректный тип данных в ответе PowerShell")


def login_exists(login: str) -> bool:
    _require_settings()
    code, out, err = run_ps(ps_check_login_exists(login))
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"WinRM status={code}")
    return out.strip().upper().startswith("YES")


def upn_exists(login: str) -> bool:
    _require_settings()
    code, out, err = run_ps(ps_check_upn_exists(login))
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"WinRM status={code}")
    return out.strip().upper().startswith("YES")


def login_or_upn_exists(login: str) -> bool:
    return login_exists(login) or upn_exists(login)


def login_or_upn_exists_many(logins: list[str]) -> set[str]:
    """Проверяет список логинов одним обращением к AD."""
    _require_settings()
    normalized = []
    seen = set()
    for login in logins:
        value = (login or "").strip().lower()
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    if not normalized:
        return set()

    data = _ensure_list(_load_json_payload(ps_check_login_candidates(normalized)))
    return {str(item.get("login", "")).strip().lower() for item in data if item.get("exists") is True}


def pick_free_login(base_login: str = "", first_name: str = "", last_name: str = "") -> str:
    """Подбирает свободный логин и проверяет все кандидаты одним запросом к AD."""
    if first_name and last_name:
        candidates = normalize_login_candidates(first_name, last_name)
        error_message = "Не удалось подобрать уникальный логин: заняты все варианты по имени, фамилии и цифровому хвосту."
    else:
        cleaned = (base_login or "").strip().lower()
        if not cleaned:
            raise ValueError("Не задан логин.")
        candidates = [cleaned]
        error_message = f"Логин уже занят в Active Directory: {cleaned}"

    candidates = list(dict.fromkeys(candidates))
    existing = login_or_upn_exists_many(candidates)

    for candidate in candidates:
        if candidate not in existing:
            return candidate

    raise ValueError(error_message)


def validate_ou_exists(ou_dn: str) -> str:
    _require_settings()
    ou_dn = (ou_dn or "").strip()
    if not ou_dn:
        raise ValueError("Путь подразделения в Active Directory не указан.")
    code, out, err = run_ps(ps_check_ou_exists(ou_dn))
    text = out.strip()
    if code != 0 or not text.upper().startswith("YES"):
        raise ValueError(err.strip() or text or f"Подразделение не найдено в Active Directory: {ou_dn}")
    parts = text.split("|", 1)
    return parts[1].strip() if len(parts) == 2 else ou_dn


def validate_ad_group_exists(identity: str) -> dict:
    _require_settings()
    identity = (identity or "").strip()
    if not identity:
        raise ValueError("DN или sAMAccountName группы не указан.")
    code, out, err = run_ps(ps_check_ad_group_exists(identity))
    text = out.strip()
    if code != 0 or not text.upper().startswith("YES"):
        raise ValueError(err.strip() or text or f"Группа не найдена в AD: {identity}")
    parts = text.split("|")
    return {
        "distinguished_name": parts[1].strip() if len(parts) > 1 else identity,
        "sam_account_name": parts[2].strip() if len(parts) > 2 else identity,
    }


def branch_is_hq(branch_key: str) -> bool:
    branch = Branch.objects.filter(key=branch_key).only("is_hq").first()
    if branch is not None:
        return branch.is_hq
    return branch_key == "hq"


def compute_groups(branch_key: str) -> list[str]:
    rule_qs = (
        DefaultAssignmentRule.objects.filter(
            branch__key=branch_key,
            is_active=True,
            group__is_active=True,
            applies_to_gender="",
        )
        .select_related("group")
        .order_by("priority", "id")
    )
    dynamic = [r.group.ad_identity for r in rule_qs if r.group.ad_identity]
    if dynamic:
        return dynamic

    if branch_is_hq(branch_key):
        return list(settings.GROUPS_HQ)
    return list(settings.GROUPS_BRANCH)


def compute_ou(branch_key: str) -> str:
    branch = Branch.objects.filter(key=branch_key, is_active=True).only("ou_dn").first()
    if branch and branch.ou_dn:
        return branch.ou_dn

    dn = settings.OU_MAP.get(branch_key)
    if not dn:
        raise ValueError(f"Не настроен путь подразделения Active Directory для филиала: {branch_key}")
    return dn


def compute_paths(branch_key: str, login: str) -> tuple[str, str]:
    if branch_is_hq(branch_key):
        return settings.PROFILE_HQ.format(login=login), settings.HOME_HQ.format(login=login)
    return settings.PROFILE_BRANCH.format(login=login), ""


def should_change_password_at_logon(branch_key: str) -> bool:
    # Первичный пароль всегда временный: пользователь должен сменить его при первом входе.
    return True


def create_user(form: dict) -> tuple[bool, str, dict | None]:
    try:
        _require_settings()

        branch_key = form["branch"]
        branch = Branch.objects.filter(key=branch_key).first()
        branch_label = branch.label if branch else settings.BRANCH_LABELS.get(branch_key)
        if not branch_label:
            raise ValueError(f"Неизвестный филиал: {branch_key}")

        manual_login = (form.get("custom_login") or "").strip()
        if manual_login:
            login = pick_free_login(manual_login)
        else:
            login = pick_free_login(first_name=form["first_name"], last_name=form["last_name"])

        birth = normalize_birth_date((form.get("birth_date") or "").strip()) or ""
        full_name = " ".join(
            part for part in [
                form["last_name"].strip(),
                form["first_name"].strip(),
                (form.get("middle_name") or "").strip(),
            ]
            if part
        )

        upn = f"{login}{settings.AD_UPN_SUFFIX}"
        profile, home = compute_paths(branch_key, login)
        target_ou = compute_ou(branch_key)
        validate_ou_exists(target_ou)

        payload = {
            "login": login,
            "full_name": full_name,
            "first_name": form["first_name"].strip(),
            "last_name": form["last_name"].strip(),
            "middle_name": (form.get("middle_name") or "").strip(),
            "birth_date": birth,
            "position": form["position"].strip(),
            "department": form["department"].strip(),
            "branch_label": branch_label,
            "branch_key": branch_key,
            "upn": upn,
            "password": settings.AD_DEFAULT_PASSWORD,
            "change_password_at_logon": should_change_password_at_logon(branch_key),
            "target_ou_dn": target_ou,
            "profile_path": profile,
            "home_directory": home,
            "groups": compute_groups(branch_key),
            "expiration_date": form["expiration_date"].isoformat() if form.get("expiration_date") else None,
        }

        code, out, err = run_ps(ps_create_user(payload))
        if code == 0 and out.strip().startswith("OK|"):
            _, lgn, upn_out, mailbox = out.strip().split("|", 3)

            msg = f"Создан пользователь: {lgn}"

            details = {
                "full_name": full_name,
                "login": lgn,
                "upn": upn_out,
                "email": "",
                "temp_password": settings.AD_DEFAULT_PASSWORD,
            }

            return True, msg, details

        return False, (err.strip() or out.strip() or f"WinRM status={code}"), None

    except Exception as e:
        return False, str(e), None


def _colorize_expiry_item(item: dict) -> dict:
    days = int(item.get("days", 0))
    if days < 0:
        color = "red"
        color_label = "Просрочен"
        days_display = f"Просрочен на {abs(days)} дн."
    elif days == 0:
        color = "red"
        color_label = "Истекает сегодня"
        days_display = "Сегодня"
    elif 7 <= days <= 10:
        color = "green"
        color_label = "Зелёная зона"
        days_display = str(days)
    elif 4 <= days <= 6:
        color = "orange"
        color_label = "Оранжевая зона"
        days_display = str(days)
    else:
        color = "red"
        color_label = "Красная зона"
        days_display = str(days)

    return {
        "login": item.get("login", ""),
        "name": item.get("name", ""),
        "days": days,
        "days_display": days_display,
        "expiry_date": item.get("expiry_date", ""),
        "color": color,
        "color_label": color_label,
    }


def _colorize_inactive_item(item: dict) -> dict:
    days_inactive = int(item.get("days_inactive", 0))
    if days_inactive >= 90:
        color = "red"
        color_label = "90+ дней"
    elif days_inactive >= 60:
        color = "orange"
        color_label = "60+ дней"
    else:
        color = "green"
        color_label = "6+ дней"

    return {
        "login": item.get("login", ""),
        "name": item.get("name", ""),
        "days_inactive": days_inactive,
        "last_logon": item.get("last_logon", ""),
        "created_at": item.get("created_at", ""),
        "color": color,
        "color_label": color_label,
    }


def get_inactive_users_bucket(min_days: int, max_days: int | None = None, search_base: str | None = None) -> list[dict]:
    data = _ensure_list(_load_json_payload(ps_get_inactive_users(days=min_days, search_base=search_base)))
    users: list[dict] = []

    for item in data:
        days_inactive = int(item.get("days_inactive", 0))
        if max_days is not None and days_inactive > max_days:
            continue
        users.append(_colorize_inactive_item(item))

    users.sort(key=lambda x: (-x["days_inactive"], x["login"]))
    return users


def get_blocked_users(search_base: str | None = None) -> list[dict]:
    data = _ensure_list(_load_json_payload(ps_get_blocked_users(search_base=search_base)))
    users: list[dict] = []
    for item in data:
        color = item.get("color") or "red"
        users.append({
            "login": item.get("login", ""),
            "name": item.get("name", ""),
            "status": item.get("status", ""),
            "last_logon": item.get("last_logon", ""),
            "created_at": item.get("created_at", ""),
            "color": color,
        })
    return users


def unlock_user(login: str) -> tuple[bool, str]:
    try:
        _require_settings()
        login = (login or "").strip()
        if not login:
            raise ValueError("Не указан логин пользователя.")

        code, out, err = run_ps(ps_unlock_user(login))
        if code == 0 and out.strip().startswith("OK|"):
            parts = out.strip().split("|")
            state = parts[1] if len(parts) > 1 else "unlocked"
            target = parts[2] if len(parts) > 2 else login
            if state == "not_locked":
                return True, f"Пользователь {target} уже разблокирован."
            return True, f"Пользователь {target} разблокирован."
        return False, (err.strip() or out.strip() or f"WinRM status={code}")
    except Exception as e:
        return False, str(e)


def _snapshot_from_payload(payload: dict, fallback_search_base: str = "") -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError("Некорректный формат агрегированной аналитики PowerShell")

    expiry_users = [_colorize_expiry_item(item) for item in _ensure_list(payload.get("expiry_users"))]
    inactive_users = [_colorize_inactive_item(item) for item in _ensure_list(payload.get("inactive_users"))]
    blocked_users = get_blocked_users(search_base=fallback_search_base) if payload.get("blocked_users") is None else [
        {
            "login": item.get("login", ""),
            "name": item.get("name", ""),
            "status": item.get("status", ""),
            "last_logon": item.get("last_logon", ""),
            "created_at": item.get("created_at", ""),
            "color": item.get("color") or "red",
        }
        for item in _ensure_list(payload.get("blocked_users"))
    ]

    inactive_30 = [u for u in inactive_users if 6 <= u["days_inactive"] <= 59]
    inactive_60 = [u for u in inactive_users if 60 <= u["days_inactive"] <= 89]
    inactive_90 = [u for u in inactive_users if u["days_inactive"] >= 90]

    stats = {
        "expiry_total": len(expiry_users),
        "inactive_30_total": len(inactive_30),
        "inactive_60_total": len(inactive_60),
        "inactive_90_total": len(inactive_90),
        "inactive_total": len(inactive_users),
        "blocked_total": len(blocked_users),
    }

    meta = payload.get("meta") or {}
    return {
        "stats": stats,
        "expiry_users": expiry_users,
        "inactive_30": inactive_30,
        "inactive_60": inactive_60,
        "inactive_90": inactive_90,
        "blocked_users": blocked_users,
        "meta": {
            "scanned_users": int(meta.get("scanned_users", 0) or 0),
            "search_base": meta.get("search_base", "") or "",
        },
    }


def get_ad_analytics_snapshot(max_days: int = 10, search_base: str | None = None) -> dict:
    payload = _load_json_payload(ps_get_ad_analytics(max_days=max_days, search_base=search_base))
    return _snapshot_from_payload(payload, fallback_search_base=search_base or "")


def monitoring_branches() -> list[dict]:
    branches = list(Branch.objects.filter(is_active=True).order_by("sort_order", "label"))
    if not branches:
        branches = [
            type("BranchFallback", (), {"key": key, "label": label, "ou_dn": settings.OU_MAP.get(key), "is_hq": key == "hq"})()
            for key, label in settings.BRANCH_LABELS.items()
            if settings.OU_MAP.get(key)
        ]
    branches.sort(key=lambda branch: (0 if getattr(branch, "is_hq", False) or branch.key == "hq" else 1, getattr(branch, "sort_order", 100), branch.label))
    return [
        {
            "key": branch.key,
            "label": branch.label,
            "search_base": branch.ou_dn,
            "is_hq": bool(getattr(branch, "is_hq", False) or branch.key == "hq"),
        }
        for branch in branches
        if branch.ou_dn
    ]


def get_ad_analytics_snapshot_by_branches(max_days: int = 10) -> dict:
    branch_items = monitoring_branches()
    branch_snapshots = {}
    for branch in branch_items:
        branch_snapshots[branch["key"]] = get_ad_analytics_snapshot(max_days=max_days, search_base=branch["search_base"])

    active_branch = branch_items[0]["key"] if branch_items else ""
    active_snapshot = branch_snapshots.get(active_branch, get_ad_analytics_snapshot(max_days=max_days))
    result = dict(active_snapshot)
    result.update({
        "monitoring_branches": branch_items,
        "branch_snapshots": branch_snapshots,
        "active_branch": active_branch,
    })
    return result
