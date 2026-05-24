from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .forms import (
    AdManagedGroupForm,
    BranchForm,
    CreateAccountForm,
    DefaultAssignmentRuleForm,
    RequiredPasswordChangeForm,
    WebRoleForm,
    WebUserCreateForm,
)
from .models import (
    ActionLog,
    AdManagedGroup,
    Branch,
    DefaultAssignmentRule,
    SYSTEM_SECTION_CHOICES,
    SystemLog,
    WEB_ROLE_OPERATOR,
    WEB_ROLE_SUPER_ADMIN,
    WebGroupRole,
    WebUserPasswordState,
)
from .passwords import generate_temporary_password
from .services.ad_logic import compute_groups, compute_ou, create_user, pick_free_login, unlock_user
from .services.monitoring import get_or_build_snapshot, refresh_snapshot, trigger_async_refresh
from .utils import normalize_birth_date

SYSTEM_SECTIONS = ["branches", "groups", "rules", "roles", "users"]
ALL_SECTION_KEYS = [key for key, _label in SYSTEM_SECTION_CHOICES]


def in_group(user, name: str) -> bool:
    return user.is_superuser or user.groups.filter(name=name).exists()


def is_super_admin(user) -> bool:
    return user.is_superuser or in_group(user, WEB_ROLE_SUPER_ADMIN)


def _user_allowed_sections(user) -> set[str]:
    if not user.is_authenticated:
        return set()
    if is_super_admin(user):
        return set(ALL_SECTION_KEYS)
    sections: set[str] = set()
    roles = WebGroupRole.objects.filter(group__user=user).select_related("group")
    for role in roles:
        if role.group.name == WEB_ROLE_OPERATOR and not role.allowed_sections:
            sections.update(["monitoring", "create_user", "logs"])
        sections.update(role.allowed_sections or [])
    return sections


def _user_allowed_branch_keys(user) -> set[str] | None:
    if not user.is_authenticated:
        return set()
    if is_super_admin(user):
        return None
    allowed: set[str] = set()
    has_unrestricted_role = False
    roles = WebGroupRole.objects.filter(group__user=user).select_related("group")
    for role in roles:
        branch_keys = role.allowed_branches or []
        if branch_keys:
            allowed.update(branch_keys)
        else:
            has_unrestricted_role = True
    if has_unrestricted_role:
        return None
    return allowed


def has_section_access(user, section: str) -> bool:
    return section in _user_allowed_sections(user)


def is_operator(user) -> bool:
    return is_super_admin(user) or bool(_user_allowed_sections(user).intersection({"monitoring", "create_user", "logs"}))


def can_monitoring(user) -> bool:
    return has_section_access(user, "monitoring")


def can_create_account(user) -> bool:
    return has_section_access(user, "create_user")


def can_view_ad_logs(user) -> bool:
    return has_section_access(user, "logs")


def can_manage_system(user) -> bool:
    return is_super_admin(user) or bool(_user_allowed_sections(user).intersection(SYSTEM_SECTIONS))


def can_manage_system_section(user, section: str) -> bool:
    return is_super_admin(user) or has_section_access(user, section)


def _apply_branch_access(snapshot: dict, user, requested_branch: str = "") -> dict:
    branches = list(snapshot.get("monitoring_branches") or [])
    allowed_keys = _user_allowed_branch_keys(user)
    if allowed_keys is not None:
        branches = [branch for branch in branches if branch.get("key") in allowed_keys]

    branch_snapshots = snapshot.get("branch_snapshots") or {}
    if not branches:
        result = dict(snapshot)
        result.update({
            "monitoring_branches": [],
            "branch_snapshots": {},
            "active_branch": "",
        })
        return result

    active_branch = requested_branch if any(branch.get("key") == requested_branch for branch in branches) else branches[0]["key"]
    active_snapshot = branch_snapshots.get(active_branch, {})
    result = dict(snapshot)
    result.update(active_snapshot)
    result.update({
        "monitoring_branches": branches,
        "branch_snapshots": {branch["key"]: branch_snapshots.get(branch["key"], {}) for branch in branches},
        "active_branch": active_branch,
        "active_branch_label": next((branch["label"] for branch in branches if branch["key"] == active_branch), active_branch),
    })
    return result


def require_test(test_func):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return view_func(request, *args, **kwargs)
            if not test_func(request.user):
                return HttpResponseForbidden("Недостаточно прав для выполнения операции")
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


@require_http_methods(["GET", "POST"])
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def change_initial_password(request):
    if request.method == "POST":
        form = RequiredPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            WebUserPasswordState.objects.update_or_create(
                user=user,
                defaults={"must_change_password": False},
            )
            update_session_auth_hash(request, user)
            messages.success(request, "Пароль изменен.")
            return redirect("index")
    else:
        form = RequiredPasswordChangeForm(request.user)

    return render(request, "registration/change_initial_password.html", {"form": form})


@login_required
def index(request):
    return ad_analytics_view(request)


@login_required
@require_test(can_create_account)
def create_account(request):
    stage = (request.POST.get("stage") or "form").strip()
    if request.method == "POST":
        form = CreateAccountForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            if stage == "form":
                try:
                    branch_key = data["branch"]
                    branch = Branch.objects.filter(key=branch_key).first()
                    branch_label = (branch.label if branch else settings.BRANCH_LABELS.get(branch_key)) or branch_key
                    manual_login = (data.get("custom_login") or "").strip()
                    if manual_login:
                        login = pick_free_login(manual_login)
                    else:
                        login = pick_free_login(first_name=data["first_name"], last_name=data["last_name"])
                    birth = normalize_birth_date((data.get("birth_date") or "").strip()) or ""
                    parts = [data["last_name"].strip(), data["first_name"].strip(), (data.get("middle_name") or "").strip()]
                    full_name = " ".join([part for part in parts if part])
                    upn = f"{login}{settings.AD_UPN_SUFFIX}"
                    preview = {
                        "full_name": full_name,
                        "login": login,
                        "upn": upn,
                        "email_hint": upn,
                        "temp_password": settings.AD_DEFAULT_PASSWORD,
                        "branch_label": branch_label,
                        "department": data["department"],
                        "position": data["position"],
                        "birth_date": birth,
                        "expiration_date": data["expiration_date"],
                        "target_ou": compute_ou(branch_key),
                        "groups": compute_groups(branch_key),
                    }
                    form.data = form.data.copy()
                    form.data["custom_login"] = login
                except Exception as exc:
                    messages.error(request, f"Не удалось сформировать предпросмотр: {exc}")
                    return render(request, "accounts/create.html", {"form": form, "stage": "form"})
                return render(request, "accounts/create.html", {"form": form, "preview": preview, "stage": "confirm"})
            if stage == "confirm":
                ok, msg, details = create_user(data)
                target_login = details["login"] if ok and details else (data.get("custom_login") or "").strip()
                ActionLog.objects.create(
                    actor=request.user,
                    action=ActionLog.ACTION_CREATE_USER,
                    target_login=target_login,
                    success=ok,
                    details=msg,
                )
                (messages.success if ok else messages.error)(request, msg)
                if ok and details:
                    return render(request, "accounts/create.html", {"form": CreateAccountForm(), "stage": "result", "result": details})
                return render(request, "accounts/create.html", {"form": form, "stage": "form"})
    else:
        form = CreateAccountForm()
    return render(request, "accounts/create.html", {"form": form, "stage": "form"})


@login_required
@require_test(can_view_ad_logs)
def logs_view(request):
    logs = ActionLog.objects.filter(action__in=ActionLog.AD_ACTIONS, success=True)[:300]
    return render(request, "accounts/logs.html", {"logs": logs, "active_panel": "ad", "log_kind": "ad"})


@login_required
@require_test(can_view_ad_logs)
def error_logs_view(request):
    logs = ActionLog.objects.filter(action__in=ActionLog.AD_ACTIONS, success=False)[:300]
    return render(request, "accounts/logs.html", {"logs": logs, "active_panel": "errors", "log_kind": "ad"})


@login_required
@require_test(is_super_admin)
def system_logs_view(request):
    logs = SystemLog.objects.all()[:300]
    return render(request, "accounts/logs.html", {"logs": logs, "active_panel": "system", "log_kind": "system"})


def _write_system_log(request, action: str, target: str, details: str, success: bool = True) -> None:
    SystemLog.objects.create(
        actor=request.user,
        action=action,
        target=target,
        success=success,
        details=details,
    )


def _first_allowed_system_section(user, preferred: str) -> str | None:
    if preferred in SYSTEM_SECTIONS and can_manage_system_section(user, preferred):
        return preferred
    for section in SYSTEM_SECTIONS:
        if can_manage_system_section(user, section):
            return section
    return None


def _ensure_section_access(request, section: str) -> bool:
    if can_manage_system_section(request.user, section):
        return True
    messages.error(request, "Недостаточно прав для выбранного раздела.")
    return False


@login_required
@require_test(can_manage_system)
def system_management_view(request):
    requested_section = (request.GET.get("section") or request.POST.get("section") or "branches").strip()
    section = _first_allowed_system_section(request.user, requested_section)
    if section is None:
        return HttpResponseForbidden("Недостаточно прав для управления системой")

    branch_form = BranchForm(prefix="branch")
    group_form = AdManagedGroupForm(prefix="adgroup")
    rule_form = DefaultAssignmentRuleForm(prefix="rule")
    role_form = WebRoleForm(prefix="role")
    user_create_form = WebUserCreateForm(prefix="webuser")
    selected_role_id = (request.POST.get("role_id") or request.GET.get("role_id") or "").strip()
    edited_role_form = None

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        action_section = {
            "create_branch": "branches",
            "delete_branch": "branches",
            "create_group": "groups",
            "delete_group": "groups",
            "create_rule": "rules",
            "delete_rule": "rules",
            "create_role": "roles",
            "update_role": "roles",
            "delete_role": "roles",
            "create_web_user": "users",
            "delete_web_user": "users",
            "change_web_user_role": "users",
        }.get(action, section)
        if not _ensure_section_access(request, action_section):
            return redirect(f"{request.path}?section={section}")
        section = action_section

        if action == "create_branch":
            branch_form = BranchForm(request.POST, prefix="branch")
            if branch_form.is_valid():
                branch = branch_form.save()
                _write_system_log(
                    request,
                    SystemLog.ACTION_CREATE_BRANCH,
                    branch.key,
                    f"Добавлен филиал {branch.label}; путь подразделения AD: {branch.ou_dn}",
                )
                messages.success(request, "Филиал добавлен.")
                return redirect(f"{request.path}?section=branches")
            messages.error(request, "Ошибка в данных филиала. Проверьте путь подразделения и доступность Active Directory.")
            section = "branches"
        elif action == "delete_branch":
            branch = get_object_or_404(Branch, pk=request.POST.get("branch_id"))
            target = branch.key
            label = branch.label
            branch.delete()
            _write_system_log(request, SystemLog.ACTION_DELETE_BRANCH, target, f"Удален филиал {label}")
            messages.success(request, "Филиал удален.")
            return redirect(f"{request.path}?section=branches")
        elif action == "create_group":
            group_form = AdManagedGroupForm(request.POST, prefix="adgroup")
            if group_form.is_valid():
                group = group_form.save()
                _write_system_log(
                    request,
                    SystemLog.ACTION_CREATE_AD_GROUP,
                    group.code,
                    f"Добавлена AD-группа {group.name}; идентификатор: {group.ad_identity}",
                )
                messages.success(request, "AD-группа добавлена.")
                return redirect(f"{request.path}?section=groups")
            messages.error(request, "Ошибка в данных группы. Укажите DN или точный sAMAccountName существующей группы AD.")
            section = "groups"
        elif action == "delete_group":
            group = get_object_or_404(AdManagedGroup, pk=request.POST.get("group_id"))
            target = group.code
            name = group.name
            group.delete()
            _write_system_log(request, SystemLog.ACTION_DELETE_AD_GROUP, target, f"Удалена AD-группа из справочника: {name}")
            messages.success(request, "AD-группа удалена из справочника веб-сервиса.")
            return redirect(f"{request.path}?section=groups")
        elif action == "create_rule":
            rule_form = DefaultAssignmentRuleForm(request.POST, prefix="rule")
            if rule_form.is_valid():
                rule = rule_form.save()
                _write_system_log(
                    request,
                    SystemLog.ACTION_CREATE_RULE,
                    rule.branch.key,
                    f"Добавлено правило: филиал {rule.branch.label}; группа {rule.group.name}",
                )
                messages.success(request, "Правило добавлено.")
                return redirect(f"{request.path}?section=rules")
            messages.error(request, "Ошибка в правиле.")
            section = "rules"
        elif action == "delete_rule":
            rule = get_object_or_404(DefaultAssignmentRule, pk=request.POST.get("rule_id"))
            target = rule.branch.key
            details = f"Удалено правило: филиал {rule.branch.label}; группа {rule.group.name}"
            rule.delete()
            _write_system_log(request, SystemLog.ACTION_DELETE_RULE, target, details)
            messages.success(request, "Правило удалено.")
            return redirect(f"{request.path}?section=rules")
        elif action == "create_role":
            role_form = WebRoleForm(request.POST, prefix="role")
            if role_form.is_valid():
                group = Group.objects.create(name=role_form.cleaned_data["name"])
                role = WebGroupRole.objects.create(
                    group=group,
                    is_system=False,
                    description=role_form.cleaned_data.get("description", ""),
                    allowed_sections=role_form.cleaned_data.get("allowed_sections", []),
                    allowed_branches=role_form.cleaned_data.get("allowed_branches", []),
                )
                _write_system_log(
                    request,
                    SystemLog.ACTION_UPSERT_ROLE,
                    role.display_name,
                    f"Создана роль; разделы: {', '.join(role.allowed_section_labels()) or 'нет'}; филиалы: {', '.join(role.allowed_branch_labels()) or 'все'}",
                )
                messages.success(request, "Роль создана.")
                return redirect(f"{request.path}?section=roles&role_id={role.pk}")
            messages.error(request, "Ошибка в данных роли.")
            section = "roles"
        elif action == "update_role":
            role = get_object_or_404(WebGroupRole.objects.select_related("group"), pk=request.POST.get("role_id"))
            selected_role_id = str(role.pk)
            edit_form = WebRoleForm(request.POST, prefix=f"role_{role.pk}", role=role)
            if edit_form.is_valid():
                old_name = role.group.name
                if not role.is_system:
                    role.group.name = edit_form.cleaned_data["name"]
                    role.group.save(update_fields=["name"])
                role.description = edit_form.cleaned_data.get("description", "")
                role.allowed_sections = edit_form.cleaned_data.get("allowed_sections", [])
                role.allowed_branches = edit_form.cleaned_data.get("allowed_branches", [])
                role.save(update_fields=["description", "allowed_sections", "allowed_branches"])
                _write_system_log(
                    request,
                    SystemLog.ACTION_UPSERT_ROLE,
                    role.display_name,
                    f"Изменена роль {old_name}; разделы: {', '.join(role.allowed_section_labels()) or 'нет'}; филиалы: {', '.join(role.allowed_branch_labels()) or 'все'}",
                )
                messages.success(request, "Роль изменена.")
                return redirect(f"{request.path}?section=roles&role_id={role.pk}")
            edited_role_form = edit_form
            role_form = WebRoleForm(prefix="role")
            messages.error(request, "Ошибка в данных роли.")
            section = "roles"
        elif action == "delete_role":
            role = get_object_or_404(WebGroupRole, pk=request.POST.get("role_id"))
            if role.is_system:
                messages.error(request, "Системную роль удалить нельзя.")
                return redirect(f"{request.path}?section=roles")
            target = role.display_name
            role.group.delete()
            _write_system_log(request, SystemLog.ACTION_DELETE_ROLE, target, "Удалена роль веб-сервиса")
            messages.success(request, "Роль удалена.")
            return redirect(f"{request.path}?section=roles")
        elif action == "create_web_user":
            user_create_form = WebUserCreateForm(request.POST, prefix="webuser")
            if user_create_form.is_valid():
                temporary_password = generate_temporary_password()
                user = User.objects.create_user(
                    username=user_create_form.cleaned_data["username"],
                    first_name=user_create_form.cleaned_data.get("first_name", ""),
                    last_name=user_create_form.cleaned_data.get("last_name", ""),
                    password=temporary_password,
                )
                WebUserPasswordState.objects.create(user=user, must_change_password=True)
                selected_role = user_create_form.cleaned_data["role"]
                user.groups.set([selected_role])
                role = getattr(selected_role, "web_role", None)
                role_name = role.display_name if role else selected_role.name
                _write_system_log(
                    request,
                    SystemLog.ACTION_CREATE_WEB_USER,
                    user.username,
                    f"Создан пользователь веб-сервиса; роль: {role_name}",
                )
                messages.success(request, f"Пользователь создан. Временный пароль: {temporary_password}")
                return redirect(f"{request.path}?section=users")
            messages.error(request, "Ошибка в данных пользователя.")
            section = "users"
        elif action == "delete_web_user":
            target_user = get_object_or_404(User, pk=request.POST.get("user_id"))
            if target_user.pk == request.user.pk:
                messages.error(request, "Нельзя удалить свою текущую учетную запись.")
            else:
                username = target_user.username
                target_user.delete()
                _write_system_log(request, SystemLog.ACTION_DELETE_WEB_USER, username, "Удален пользователь веб-сервиса")
                messages.success(request, "Пользователь удален.")
            return redirect(f"{request.path}?section=users")
        elif action == "change_web_user_role":
            target_user = get_object_or_404(User, pk=request.POST.get("user_id"))
            role = get_object_or_404(
                WebGroupRole.objects.select_related("group").exclude(group__name="AD Admins"),
                pk=request.POST.get("role_id"),
            )
            existing_roles = [r.display_name for r in WebGroupRole.objects.select_related("group") if target_user.groups.filter(pk=r.group_id).exists()]
            old_roles = ", ".join(existing_roles) or "без роли"
            web_role_groups = [r.group for r in WebGroupRole.objects.select_related("group")]
            target_user.groups.remove(*web_role_groups)
            target_user.groups.add(role.group)
            _write_system_log(
                request,
                SystemLog.ACTION_UPDATE_WEB_ACCESS,
                target_user.username,
                f"Изменена роль пользователя веб-сервиса: {old_roles} -> {role.display_name}",
            )
            messages.success(request, "Роль пользователя изменена.")
            return redirect(f"{request.path}?section=users")

    web_roles = WebGroupRole.objects.select_related("group").exclude(group__name="AD Admins")
    selected_role = None
    selected_role_form = None
    if selected_role_id:
        try:
            selected_role = web_roles.get(pk=selected_role_id)
        except (TypeError, ValueError, WebGroupRole.DoesNotExist):
            selected_role = None
        if selected_role is not None:
            selected_role_form = edited_role_form or WebRoleForm(prefix=f"role_{selected_role.pk}", role=selected_role)
    context = {
        "section": section,
        "system_sections": SYSTEM_SECTIONS,
        "branch_form": branch_form,
        "group_form": group_form,
        "rule_form": rule_form,
        "role_form": role_form,
        "user_create_form": user_create_form,
        "branches": Branch.objects.all(),
        "managed_groups": AdManagedGroup.objects.all(),
        "rules": DefaultAssignmentRule.objects.select_related("branch", "group").filter(is_active=True, applies_to_gender=""),
        "web_roles": web_roles,
        "selected_role": selected_role,
        "selected_role_form": selected_role_form,
        "role_options": web_roles.order_by("group__name"),
        "web_users": User.objects.prefetch_related("groups", "groups__web_role").order_by("username"),
        "can_system_log": is_super_admin(request.user),
    }
    return render(request, "accounts/super_admin.html", context)


def _analytics_context() -> dict:
    try:
        snapshot = get_or_build_snapshot()
    except Exception as exc:
        snapshot = {
            "stats": {
                "expiry_total": 0,
                "inactive_30_total": 0,
                "inactive_60_total": 0,
                "inactive_90_total": 0,
                "inactive_total": 0,
                "blocked_total": 0,
            },
            "expiry_users": [],
            "inactive_30": [],
            "inactive_60": [],
            "inactive_90": [],
            "blocked_users": [],
            "meta": {"scanned_users": 0, "search_base": getattr(settings, "AD_USERS_SEARCH_BASE", "") or ""},
            "monitoring_status": "error",
            "monitoring_error": str(exc),
            "monitoring_updated_at": "",
            "monitoring_generated_in_ms": 0,
            "monitoring_cache_backend": "unknown",
            "monitoring_source": "error",
            "monitoring_poll_seconds": settings.MONITORING_FRAGMENT_POLL_SECONDS,
        }
    return snapshot


@login_required
@require_test(can_monitoring)
def ad_analytics_view(request):
    context = _apply_branch_access(_analytics_context(), request.user, (request.GET.get("branch") or "").strip())
    if context.get("monitoring_status") == "warming_up":
        trigger_async_refresh()
    return render(request, "accounts/ad_analytics.html", context)


@login_required
@require_test(can_monitoring)
@require_GET
def ad_analytics_fragment_view(request):
    context = _apply_branch_access(_analytics_context(), request.user, (request.GET.get("branch") or "").strip())
    html = render_to_string("accounts/ad_analytics_content.html", context, request=request)
    return JsonResponse({"ok": True, "html": html, "updated_at": context.get("monitoring_updated_at", "")})


@login_required
@require_test(can_monitoring)
@require_POST
def unlock_user_view(request):
    login = (request.POST.get("login") or "").strip()
    ok, msg = unlock_user(login)
    ActionLog.objects.create(
        actor=request.user,
        action=ActionLog.ACTION_UNLOCK_USER,
        target_login=login,
        success=ok,
        details=msg,
    )
    if ok:
        try:
            snapshot = refresh_snapshot()
            context = _apply_branch_access(snapshot, request.user, (request.POST.get("branch") or "").strip())
            return JsonResponse({"ok": True, "message": msg, "updated_at": context.get("monitoring_updated_at", "")})
        except Exception:
            trigger_async_refresh()
            return JsonResponse({"ok": True, "message": msg})
    return JsonResponse({"ok": False, "message": msg}, status=400)


@login_required
@require_test(can_monitoring)
@require_GET
def ad_analytics_refresh_view(request):
    mode = (request.GET.get("mode") or "async").strip().lower()
    if mode == "sync":
        try:
            snapshot = refresh_snapshot()
        except Exception as exc:
            return JsonResponse({"ok": False, "mode": "sync", "message": str(exc)}, status=503)
        context = _apply_branch_access(snapshot, request.user, (request.GET.get("branch") or "").strip())
        return JsonResponse({"ok": True, "mode": "sync", "updated_at": context.get("monitoring_updated_at", "")})

    queued = trigger_async_refresh()
    if queued:
        return JsonResponse({"ok": True, "mode": "async"})
    return JsonResponse({"ok": False, "mode": "async", "message": "Не удалось поставить задачу обновления мониторинга в очередь Celery."}, status=503)
