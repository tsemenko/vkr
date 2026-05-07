from __future__ import annotations

import json
from typing import Any

from django.conf import settings

from ..models import Branch, DefaultAssignmentRule
from ..utils import normalize_birth_date, normalize_login
from .powershell import (
    ps_check_login_exists,
    ps_check_upn_exists,
    ps_create_user,
    ps_get_inactive_users,
    ps_get_blocked_users,
    ps_get_ad_analytics,
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


def pick_free_login(base_login: str) -> str:
    if not login_or_upn_exists(base_login):
        return base_login
    for i in range(1, 100):
        cand = f"{base_login}{i}"
        if not login_or_upn_exists(cand):
            return cand
    raise ValueError("Не удалось подобрать уникальный логин (заняты варианты 1..99).")

def branch_is_hq(branch_key: str) -> bool:
    branch = Branch.objects.filter(key=branch_key).only("is_hq").first()
    if branch is not None:
        return branch.is_hq
    return branch_key == "hq"

def compute_groups(branch_key: str, gender: str) -> list[str]:
    rule_qs = (
        DefaultAssignmentRule.objects.filter(branch__key=branch_key, is_active=True, group__is_active=True)
        .select_related("group")
        .order_by("priority", "id")
    )
    dynamic = [r.group.name for r in rule_qs if not r.applies_to_gender or r.applies_to_gender == gender]
    if dynamic:
        return dynamic

    if branch_is_hq(branch_key):
        groups = list(settings.GROUPS_HQ)
        if gender == "F":
            groups += list(settings.GROUPS_HQ_F)
        return groups
    groups = list(settings.GROUPS_BRANCH)
    if gender == "F":
        groups += list(settings.GROUPS_BRANCH_F)
    return groups

def compute_ou(branch_key: str) -> str:
    branch = Branch.objects.filter(key=branch_key, is_active=True).only("ou_dn").first()
    if branch and branch.ou_dn:
        return branch.ou_dn

    dn = settings.OU_MAP.get(branch_key)
    if not dn:
        raise ValueError(f"Не настроен OU DN для филиала: {branch_key}")
    return dn

def compute_paths(branch_key: str, login: str) -> tuple[str, str]:
    if branch_is_hq(branch_key):
        return settings.PROFILE_HQ.format(login=login), settings.HOME_HQ.format(login=login)
    return settings.PROFILE_BRANCH.format(login=login), ""

def should_change_password_at_logon(branch_key: str) -> bool:
    # Для головного вуза включаем смену пароля при первом входе.
    return branch_is_hq(branch_key)

def create_user(form: dict) -> tuple[bool, str, dict | None]:
    try:
        _require_settings()

        branch_key = form["branch"]
        branch = Branch.objects.filter(key=branch_key).first()
        branch_label = branch.label if branch else settings.BRANCH_LABELS.get(branch_key)
        if not branch_label:
            raise ValueError(f"Неизвестный филиал: {branch_key}")

        base_login = (form.get("custom_login") or "").strip()
        if not base_login:
            base_login = normalize_login(form["first_name"], form["last_name"])
        login = pick_free_login(base_login)

        birth = normalize_birth_date((form.get("birth_date") or "").strip()) or ""

        parts = [
            form["last_name"].strip(),
            form["first_name"].strip(),
            (form.get("middle_name") or "").strip(),
        ]
        full_name = " ".join([p for p in parts if p])

        upn = f"{login}{settings.AD_UPN_SUFFIX}"
        profile, home = compute_paths(branch_key, login)

        payload = {
            "login": login,
            "full_name": full_name,
            "first_name": form["first_name"].strip(),
            "last_name": form["last_name"].strip(),
            "middle_name": (form.get("middle_name") or "").strip(),
            "gender": form["gender"],
            "birth_date": birth,
            "position": form["position"].strip(),
            "department": form["department"].strip(),
            "branch_label": branch_label,
            "branch_key": branch_key,
            "upn": upn,
            "password": settings.AD_DEFAULT_PASSWORD,
            "change_password_at_logon": should_change_password_at_logon(branch_key),
            "target_ou_dn": compute_ou(branch_key),
            "profile_path": profile,
            "home_directory": home,
            "groups": compute_groups(branch_key, form["gender"]),
            "expiration_date": form["expiration_date"].isoformat() if form.get("expiration_date") else None,
        }

        code, out, err = run_ps(ps_create_user(payload))
        if code == 0 and out.strip().startswith("OK|"):
            _, lgn, upn_out, mailbox = out.strip().split("|", 3)

            msg = f"Создан пользователь: {lgn}; UPN: {upn_out}"
            if mailbox:
                msg += f"; Почта: {mailbox}"

            details = {
                "full_name": full_name,
                "login": lgn,
                "upn": upn_out,
                "email": (mailbox or upn_out),
                "temp_password": settings.AD_DEFAULT_PASSWORD,
            }

            return True, msg, details

        return False, (err.strip() or out.strip() or f"WinRM status={code}"), None

    except Exception as e:
        return False, str(e), None


def _load_json_payload(script: str) -> Any:
    _require_settings()
    code, out, err = run_ps(script)
    if code != 0:
        raise RuntimeError(err.strip() or out.strip() or f"WinRM status={code}")

    payload = (out or '').strip()
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

def _colorize_expiry_item(item: dict) -> dict:
    days = int(item.get('days', 0))
    if days < 0:
        color = 'red'
        color_label = 'Просрочен'
        days_display = f'Просрочен на {abs(days)} дн.'
    elif days == 0:
        color = 'red'
        color_label = 'Истекает сегодня'
        days_display = 'Сегодня'
    elif 7 <= days <= 10:
        color = 'green'
        color_label = 'Зелёная зона'
        days_display = str(days)
    elif 4 <= days <= 6:
        color = 'orange'
        color_label = 'Оранжевая зона'
        days_display = str(days)
    else:
        color = 'red'
        color_label = 'Красная зона'
        days_display = str(days)

    return {
        'login': item.get('login', ''),
        'name': item.get('name', ''),
        'days': days,
        'days_display': days_display,
        'expiry_date': item.get('expiry_date', ''),
        'color': color,
        'color_label': color_label,
    }

def _colorize_inactive_item(item: dict) -> dict:
    days_inactive = int(item.get('days_inactive', 0))
    if days_inactive >= 90:
        color = 'red'
        color_label = '90+ дней'
    elif days_inactive >= 60:
        color = 'orange'
        color_label = '60+ дней'
    else:
        color = 'green'
        color_label = '6+ дней'

    return {
        'login': item.get('login', ''),
        'name': item.get('name', ''),
        'days_inactive': days_inactive,
        'last_logon': item.get('last_logon', ''),
        'created_at': item.get('created_at', ''),
        'color': color,
        'color_label': color_label,
    }


def get_inactive_users_bucket(min_days: int, max_days: int | None = None) -> list[dict]:
    data = _ensure_list(_load_json_payload(ps_get_inactive_users(days=min_days)))
    users: list[dict] = []

    for item in data:
        days_inactive = int(item.get('days_inactive', 0))
        if max_days is not None and days_inactive > max_days:
            continue
        users.append(_colorize_inactive_item(item))

    users.sort(key=lambda x: (-x['days_inactive'], x['login']))
    return users

def get_blocked_users() -> list[dict]:
    data = _ensure_list(_load_json_payload(ps_get_blocked_users()))
    users: list[dict] = []
    for item in data:
        color = item.get('color') or 'red'
        users.append({
            'login': item.get('login', ''),
            'name': item.get('name', ''),
            'status': item.get('status', ''),
            'last_logon': item.get('last_logon', ''),
            'created_at': item.get('created_at', ''),
            'color': color,
        })
    return users



def unlock_user(login: str) -> tuple[bool, str]:
    try:
        _require_settings()
        login = (login or '').strip()
        if not login:
            raise ValueError('Не указан логин пользователя.')

        code, out, err = run_ps(ps_unlock_user(login))
        if code == 0 and out.strip().startswith('OK|'):
            parts = out.strip().split('|')
            state = parts[1] if len(parts) > 1 else 'unlocked'
            target = parts[2] if len(parts) > 2 else login
            if state == 'not_locked':
                return True, f'Пользователь {target} уже разблокирован.'
            return True, f'Пользователь {target} разблокирован.'
        return False, (err.strip() or out.strip() or f'WinRM status={code}')
    except Exception as e:
        return False, str(e)

def get_ad_analytics_snapshot(max_days: int = 10) -> dict:
    payload = _load_json_payload(ps_get_ad_analytics(max_days=max_days))
    if not isinstance(payload, dict):
        raise RuntimeError('Некорректный формат агрегированной аналитики PowerShell')

    expiry_users = [_colorize_expiry_item(item) for item in _ensure_list(payload.get('expiry_users'))]
    inactive_users = [_colorize_inactive_item(item) for item in _ensure_list(payload.get('inactive_users'))]
    blocked_users = get_blocked_users() if payload.get('blocked_users') is None else [
        {
            'login': item.get('login', ''),
            'name': item.get('name', ''),
            'status': item.get('status', ''),
            'last_logon': item.get('last_logon', ''),
            'created_at': item.get('created_at', ''),
            'color': item.get('color') or 'red',
        }
        for item in _ensure_list(payload.get('blocked_users'))
    ]

    inactive_30 = [u for u in inactive_users if 6 <= u['days_inactive'] <= 59]
    inactive_60 = [u for u in inactive_users if 60 <= u['days_inactive'] <= 89]
    inactive_90 = [u for u in inactive_users if u['days_inactive'] >= 90]

    stats = {
        'expiry_total': len(expiry_users),
        'inactive_30_total': len(inactive_30),
        'inactive_60_total': len(inactive_60),
        'inactive_90_total': len(inactive_90),
        'inactive_total': len(inactive_users),
        'blocked_total': len(blocked_users),
    }

    meta = payload.get('meta') or {}
    return {
        'stats': stats,
        'expiry_users': expiry_users,
        'inactive_30': inactive_30,
        'inactive_60': inactive_60,
        'inactive_90': inactive_90,
        'blocked_users': blocked_users,
        'meta': {
            'scanned_users': int(meta.get('scanned_users', 0) or 0),
            'search_base': meta.get('search_base', '') or '',
        },
    }
