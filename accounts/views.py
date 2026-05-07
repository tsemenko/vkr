from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group, User
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    AdManagedGroupForm,
    BranchForm,
    CreateAccountForm,
    DefaultAssignmentRuleForm,
    WebRoleForm,
    WebUserAccessForm,
    WebUserCreateForm,
)
from .models import ActionLog, AdManagedGroup, Branch, DefaultAssignmentRule, WebGroupRole
from .services.ad_logic import compute_groups, compute_ou, create_user, pick_free_login, unlock_user
from .services.monitoring import get_or_build_snapshot, refresh_snapshot, trigger_async_refresh
from .utils import normalize_birth_date, normalize_login

SYSTEM_SECTIONS = {"branches", "groups", "rules", "roles", "access", "users"}

def in_group(user, name: str) -> bool:
    return user.is_superuser or user.groups.filter(name=name).exists()

def is_operator(user) -> bool:
    return in_group(user, "AD Operators") or in_group(user, "AD Admins")

def is_admin(user) -> bool:
    return in_group(user, "AD Admins")

def is_super_admin(user) -> bool:
    return user.is_superuser or in_group(user, "AD Super Admins")

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

@login_required
def index(request):
    return ad_analytics_view(request)

@login_required
@require_test(is_operator)
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
                    base_login = (data.get("custom_login") or "").strip() or normalize_login(data["first_name"], data["last_name"])
                    login = pick_free_login(base_login)
                    birth = normalize_birth_date((data.get("birth_date") or "").strip()) or ""
                    parts = [data["last_name"].strip(), data["first_name"].strip(), (data.get("middle_name") or "").strip()]
                    full_name = " ".join([part for part in parts if part])
                    upn = f"{login}{settings.AD_UPN_SUFFIX}"
                    preview = {
                        "full_name": full_name, "login": login, "upn": upn, "email_hint": upn,
                        "temp_password": settings.AD_DEFAULT_PASSWORD, "branch_label": branch_label,
                        "department": data["department"], "position": data["position"], "gender": data["gender"],
                        "gender_label": "Мужской" if data["gender"] == "M" else "Женский",
                        "birth_date": birth, "expiration_date": data["expiration_date"],
                        "target_ou": compute_ou(branch_key), "groups": compute_groups(branch_key, data["gender"]),
                    }
                    form.data = form.data.copy()
                    form.data["custom_login"] = login
                except Exception as exc:
                    messages.error(request, f"Не удалось сформировать предпросмотр: {exc}")
                    return render(request, "accounts/create.html", {"form": form, "stage": "form"})
                return render(request, "accounts/create.html", {"form": form, "preview": preview, "stage": "confirm"})
            if stage == "confirm":
                ok, msg, details = create_user(data)
                ActionLog.objects.create(actor=request.user, action="create_user", target_login=(data.get("custom_login") or "").strip(), success=ok, details=msg)
                (messages.success if ok else messages.error)(request, msg)
                if ok and details:
                    return render(request, "accounts/create.html", {"form": CreateAccountForm(), "stage": "result", "result": details})
                return render(request, "accounts/create.html", {"form": form, "stage": "form"})
    else:
        form = CreateAccountForm()
    return render(request, "accounts/create.html", {"form": form, "stage": "form"})

@login_required
@require_test(is_admin)
def logs_view(request):
    logs = ActionLog.objects.filter(success=True).order_by("-created_at")[:300]
    return render(request, "accounts/logs.html", {"logs": logs, "active_panel": "success"})

@login_required
@require_test(is_admin)
def error_logs_view(request):
    logs = ActionLog.objects.filter(success=False).order_by("-created_at")[:300]
    return render(request, "accounts/logs.html", {"logs": logs, "active_panel": "errors"})

@login_required
@require_test(is_super_admin)
def system_management_view(request):
    section = (request.GET.get("section") or request.POST.get("section") or "branches").strip()
    if section not in SYSTEM_SECTIONS:
        section = "branches"
    branch_form = BranchForm(prefix="branch")
    group_form = AdManagedGroupForm(prefix="adgroup")
    rule_form = DefaultAssignmentRuleForm(prefix="rule")
    role_form = WebRoleForm(prefix="role")
    access_form = WebUserAccessForm(prefix="access")
    user_create_form = WebUserCreateForm(prefix="webuser")
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "create_branch":
            branch_form = BranchForm(request.POST, prefix="branch")
            if branch_form.is_valid():
                branch = branch_form.save()
                ActionLog.objects.create(actor=request.user, action="system_create_branch", target_login=branch.key, success=True, details=f"Создан филиал {branch.label}")
                messages.success(request, "Филиал создан.")
                return redirect(f"{request.path}?section=branches")
            messages.error(request, "Ошибка в данных филиала.")
            section = "branches"
        elif action == "create_group":
            group_form = AdManagedGroupForm(request.POST, prefix="adgroup")
            if group_form.is_valid():
                group = group_form.save()
                ActionLog.objects.create(actor=request.user, action="system_create_ad_group", target_login=group.code, success=True, details=f"Создана AD-группа {group.name}")
                messages.success(request, "AD-группа создана.")
                return redirect(f"{request.path}?section=groups")
            messages.error(request, "Ошибка в данных группы.")
            section = "groups"
        elif action == "create_rule":
            rule_form = DefaultAssignmentRuleForm(request.POST, prefix="rule")
            if rule_form.is_valid():
                rule = rule_form.save()
                ActionLog.objects.create(actor=request.user, action="system_create_rule", target_login=rule.branch.key, success=True, details=f"Правило: {rule}")
                messages.success(request, "Правило добавлено.")
                return redirect(f"{request.path}?section=rules")
            messages.error(request, "Ошибка в правиле.")
            section = "rules"
        elif action == "create_role":
            role_form = WebRoleForm(request.POST, prefix="role")
            if role_form.is_valid():
                role_name = role_form.cleaned_data["name"].strip()
                group, created = Group.objects.get_or_create(name=role_name)
                group.permissions.set(role_form.cleaned_data["permissions"])
                WebGroupRole.objects.update_or_create(group=group, defaults={"description": role_form.cleaned_data.get("description", "").strip(), "is_system": False})
                ActionLog.objects.create(actor=request.user, action="system_upsert_role", target_login=group.name, success=True, details="Создана роль" if created else "Обновлена роль")
                messages.success(request, "Роль сохранена.")
                return redirect(f"{request.path}?section=roles")
            messages.error(request, "Ошибка в роли.")
            section = "roles"
        elif action == "grant_user_access":
            access_form = WebUserAccessForm(request.POST, prefix="access")
            if access_form.is_valid():
                target_user = access_form.cleaned_data["user"]
                target_user.groups.set(access_form.cleaned_data["groups"])
                target_user.is_active = access_form.cleaned_data["is_active"]
                target_user.is_staff = access_form.cleaned_data["is_staff"]
                target_user.save(update_fields=["is_active", "is_staff"])
                ActionLog.objects.create(actor=request.user, action="system_update_web_access", target_login=target_user.username, success=True, details="Обновлены роли пользователя веб-интерфейса")
                messages.success(request, "Доступ пользователя обновлен.")
                return redirect(f"{request.path}?section=access")
            messages.error(request, "Ошибка в настройках доступа пользователя.")
            section = "access"
        elif action == "create_web_user":
            user_create_form = WebUserCreateForm(request.POST, prefix="webuser")
            if user_create_form.is_valid():
                user = User.objects.create_user(username=user_create_form.cleaned_data["username"], first_name=user_create_form.cleaned_data.get("first_name", ""), last_name=user_create_form.cleaned_data.get("last_name", ""), email=user_create_form.cleaned_data.get("email", ""))
                user.set_unusable_password()
                user.is_active = user_create_form.cleaned_data["is_active"]
                user.is_staff = user_create_form.cleaned_data["is_staff"]
                user.save(update_fields=["password", "is_active", "is_staff"])
                user.groups.set(user_create_form.cleaned_data["groups"])
                ActionLog.objects.create(actor=request.user, action="system_create_web_user", target_login=user.username, success=True, details="Создан пользователь веб-интерфейса")
                messages.success(request, "Пользователь веб-интерфейса создан.")
                return redirect(f"{request.path}?section=users")
            messages.error(request, "Ошибка в данных пользователя.")
            section = "users"
    context = {"section": section, "branch_form": branch_form, "group_form": group_form, "rule_form": rule_form, "role_form": role_form, "access_form": access_form, "user_create_form": user_create_form, "branches": Branch.objects.all(), "managed_groups": AdManagedGroup.objects.all(), "rules": DefaultAssignmentRule.objects.select_related("branch", "group").all(), "web_roles": WebGroupRole.objects.select_related("group").prefetch_related("group__permissions").all(), "web_users": User.objects.prefetch_related("groups").order_by("username")}
    return render(request, "accounts/super_admin.html", context)

def _analytics_context(force_refresh: bool = False) -> dict:
    try:
        snapshot = refresh_snapshot() if force_refresh else get_or_build_snapshot()
    except Exception as exc:
        snapshot = {"stats": {"expiry_total": 0, "inactive_30_total": 0, "inactive_60_total": 0, "inactive_90_total": 0, "inactive_total": 0, "blocked_total": 0}, "expiry_users": [], "inactive_30": [], "inactive_60": [], "inactive_90": [], "blocked_users": [], "meta": {"scanned_users": 0, "search_base": getattr(settings, "AD_USERS_SEARCH_BASE", "") or ""}, "monitoring_status": "error", "monitoring_error": str(exc), "monitoring_updated_at": "", "monitoring_generated_in_ms": 0, "monitoring_cache_backend": "unknown", "monitoring_source": "error", "monitoring_poll_seconds": settings.MONITORING_FRAGMENT_POLL_SECONDS}
    return snapshot

@login_required
@require_test(is_operator)
def ad_analytics_view(request):
    context = _analytics_context()
    if context.get("monitoring_status") == "warming_up":
        trigger_async_refresh()
    return render(request, "accounts/ad_analytics.html", context)

@login_required
@require_test(is_operator)
@require_GET
def ad_analytics_fragment_view(request):
    force_refresh = request.GET.get("refresh") in {"1", "true", "yes"}
    context = _analytics_context(force_refresh=force_refresh)
    html = render_to_string("accounts/ad_analytics_content.html", context, request=request)
    return JsonResponse({"ok": True, "html": html, "updated_at": context.get("monitoring_updated_at", "")})

@login_required
@require_test(is_operator)
@require_POST
def unlock_user_view(request):
    login = (request.POST.get("login") or "").strip()
    ok, msg = unlock_user(login)
    ActionLog.objects.create(actor=request.user, action="unlock_user", target_login=login, success=ok, details=msg)
    if ok:
        snapshot = refresh_snapshot()
        return JsonResponse({"ok": True, "message": msg, "updated_at": snapshot.get("monitoring_updated_at", "")})
    return JsonResponse({"ok": False, "message": msg}, status=400)

@login_required
@require_test(is_operator)
@require_GET
def ad_analytics_refresh_view(request):
    mode = (request.GET.get("mode") or "async").strip().lower()
    if mode == "sync":
        snapshot = refresh_snapshot()
        return JsonResponse({"ok": True, "mode": "sync", "updated_at": snapshot.get("monitoring_updated_at", "")})
    queued = trigger_async_refresh()
    if queued:
        return JsonResponse({"ok": True, "mode": "async"})
    snapshot = refresh_snapshot()
    return JsonResponse({"ok": True, "mode": "sync", "updated_at": snapshot.get("monitoring_updated_at", "")})
