from django import forms
from django.db.models import Q
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import Group, User

from .models import (
    AdManagedGroup,
    Branch,
    DefaultAssignmentRule,
    SYSTEM_SECTION_CHOICES,
)
from .services.ad_logic import validate_ad_group_exists, validate_ou_exists
from .utils import normalize_birth_date, normalize_login


def _first_ou_name(dn: str) -> str:
    first_part = (dn or "").split(",", 1)[0].strip()
    if first_part.lower().startswith("ou="):
        return first_part[3:].strip()
    return ""


def _same_text(left: str, right: str) -> bool:
    return (left or "").strip().casefold() == (right or "").strip().casefold()


class RoleChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        role = getattr(obj, "web_role", None)
        if role:
            return role.display_name
        if obj.name == "AD Super Admins":
            return "Супер-админ"
        if obj.name == "AD Operators":
            return "Оператор"
        return obj.name


class CreateAccountForm(forms.Form):
    last_name = forms.CharField(label="Фамилия", max_length=80)
    first_name = forms.CharField(label="Имя", max_length=80)
    middle_name = forms.CharField(label="Отчество", max_length=80, required=False)
    birth_date = forms.CharField(label="Дата рождения", required=True, max_length=10)
    position = forms.CharField(label="Должность", max_length=120)
    department = forms.CharField(label="Отдел", max_length=120)
    branch = forms.ChoiceField(label="Филиал")
    custom_login = forms.CharField(label="Логин", required=False, max_length=64)
    expiration_date = forms.DateField(
        label="Срок действия учетной записи",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    field_order = [
        "last_name",
        "first_name",
        "middle_name",
        "birth_date",
        "position",
        "department",
        "branch",
        "custom_login",
        "expiration_date",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True).order_by("sort_order", "label")
        choices = [(branch.key, branch.label) for branch in branches]
        if not choices:
            from django.conf import settings

            choices = [(key, label) for key, label in settings.BRANCH_LABELS.items() if label]
        self.fields["branch"].choices = choices
        self.fields["birth_date"].widget.attrs.update({"placeholder": "ДД.ММ.ГГГГ", "id": "birth_date", "autocomplete": "off"})

    def clean_birth_date(self):
        value = (self.cleaned_data.get("birth_date") or "").strip()
        normalized = normalize_birth_date(value)
        if not normalized:
            raise forms.ValidationError("Укажите дату рождения в формате ДД.ММ.ГГГГ.")
        return normalized

    def clean_custom_login(self):
        return normalize_login(self.cleaned_data.get("custom_login", ""))


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ["key", "label", "ou_dn"]
        labels = {
            "key": "Код филиала",
            "label": "Название филиала",
            "ou_dn": "Путь подразделения в Active Directory",
        }

    def clean(self):
        cleaned = super().clean()
        key = (cleaned.get("key") or "").strip()
        ou_dn = (cleaned.get("ou_dn") or "").strip()

        if not key or not ou_dn:
            return cleaned

        try:
            resolved_dn = validate_ou_exists(ou_dn)
        except Exception as exc:
            raise forms.ValidationError({"ou_dn": str(exc)})

        ou_name = _first_ou_name(resolved_dn)
        if ou_name and not _same_text(key, ou_name):
            raise forms.ValidationError({
                "key": f"Код филиала должен совпадать с именем OU в Active Directory: {ou_name}."
            })

        duplicate = Branch.objects.exclude(pk=self.instance.pk).filter(ou_dn__iexact=resolved_dn).exists()
        if duplicate:
            raise forms.ValidationError({
                "ou_dn": "Этот путь подразделения Active Directory уже добавлен в справочник филиалов."
            })

        cleaned["key"] = key
        cleaned["ou_dn"] = resolved_dn
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.is_active = True
        obj.is_hq = False
        obj.sort_order = obj.sort_order or 100
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class AdManagedGroupForm(forms.ModelForm):
    dn = forms.CharField(label="DN или sAMAccountName группы", max_length=512, required=True)

    class Meta:
        model = AdManagedGroup
        fields = ["code", "name", "dn"]
        labels = {
            "code": "Код в системе",
            "name": "Отображаемое название",
            "dn": "DN или sAMAccountName группы",
        }

    def clean(self):
        cleaned = super().clean()
        code = (cleaned.get("code") or "").strip()
        identity = (cleaned.get("dn") or "").strip()

        if not code or not identity:
            return cleaned

        try:
            group_info = validate_ad_group_exists(identity)
        except Exception as exc:
            raise forms.ValidationError({"dn": str(exc)})

        sam_account_name = (group_info.get("sam_account_name") or "").strip()
        distinguished_name = (group_info.get("distinguished_name") or "").strip()

        if sam_account_name and not _same_text(code, sam_account_name):
            raise forms.ValidationError({
                "code": f"Код группы должен совпадать с sAMAccountName группы в Active Directory: {sam_account_name}."
            })

        duplicate = AdManagedGroup.objects.exclude(pk=self.instance.pk).filter(
            Q(dn__iexact=identity) | Q(dn__iexact=sam_account_name) | Q(dn__iexact=distinguished_name)
        ).exists()
        if duplicate:
            raise forms.ValidationError({
                "dn": "Эта группа Active Directory уже добавлена в справочник."
            })

        cleaned["code"] = code
        cleaned["dn"] = identity
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.is_active = True
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class DefaultAssignmentRuleForm(forms.ModelForm):
    class Meta:
        model = DefaultAssignmentRule
        fields = ["branch", "group"]
        labels = {
            "branch": "Филиал",
            "group": "AD-группа",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = Branch.objects.filter(is_active=True).order_by("sort_order", "label")
        self.fields["group"].queryset = AdManagedGroup.objects.filter(is_active=True).order_by("name")

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.applies_to_gender = ""
        obj.source = DefaultAssignmentRule.SOURCE_AD
        obj.priority = 100
        obj.is_active = True
        if commit:
            obj.save()
            self.save_m2m()
        return obj


def _allowed_role_queryset():
    return Group.objects.filter(web_role__isnull=False).exclude(name="AD Admins").order_by("name")


class WebRoleForm(forms.Form):
    name = forms.CharField(label="Название роли", max_length=150)
    description = forms.CharField(
        label="Описание",
        required=False,
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    allowed_sections = forms.MultipleChoiceField(
        label="Разделы системы",
        choices=SYSTEM_SECTION_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    allowed_branches = forms.MultipleChoiceField(
        label="Филиалы для мониторинга",
        choices=[],
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Если ничего не выбрано, роль видит все филиалы.",
    )

    def __init__(self, *args, **kwargs):
        self.role = kwargs.pop("role", None)
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True).order_by("sort_order", "label")
        self.fields["allowed_branches"].choices = [(branch.key, branch.label) for branch in branches]
        if self.role is not None:
            self.fields["name"].initial = self.role.group.name
            self.fields["description"].initial = self.role.description
            self.fields["allowed_sections"].initial = self.role.allowed_sections or []
            self.fields["allowed_branches"].initial = self.role.allowed_branches or []
            if self.role.is_system:
                self.fields["name"].disabled = True
                self.fields["name"].help_text = "Название системной роли нельзя менять."

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Укажите название роли.")
        if name == "AD Admins":
            raise forms.ValidationError("Эта роль не используется.")
        roles = Group.objects.filter(name=name)
        if self.role is not None:
            roles = roles.exclude(pk=self.role.group_id)
        if roles.exists():
            raise forms.ValidationError("Роль с таким названием уже существует.")
        return name


class WebUserCreateForm(forms.Form):
    username = forms.CharField(label="Логин", max_length=150)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    role = RoleChoiceField(label="Роль", queryset=Group.objects.none(), empty_label=None)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = _allowed_role_queryset()

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("Укажите логин пользователя.")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже есть в веб-сервисе.")
        return username


class RequiredPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(
        label="Временный пароль",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    new_password1 = forms.CharField(
        label="Новый пароль",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    new_password2 = forms.CharField(
        label="Повторите новый пароль",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
