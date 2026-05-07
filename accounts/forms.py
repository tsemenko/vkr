from django import forms
from django.contrib.auth.models import Group, Permission, User

from .models import AdManagedGroup, Branch, DefaultAssignmentRule

GENDER_CHOICES = [("M", "Мужской"), ("F", "Женский")]


class CreateAccountForm(forms.Form):
    last_name = forms.CharField(label="Фамилия", max_length=64)
    first_name = forms.CharField(label="Имя", max_length=64)
    middle_name = forms.CharField(label="Отчество", max_length=64, required=False)
    gender = forms.ChoiceField(label="Пол", choices=GENDER_CHOICES)
    birth_date = forms.CharField(
        label="Дата рождения в формате ДД.ММ.0004",
        max_length=10,
        required=False,
        widget=forms.TextInput(attrs={"id": "birth_date", "placeholder": "ДД.ММ.0004", "inputmode": "numeric", "autocomplete": "off"}),
    )
    position = forms.CharField(label="Должность", max_length=128)
    department = forms.CharField(label="Отдел", max_length=128)
    branch = forms.ChoiceField(label="Филиал", choices=[])
    custom_login = forms.CharField(label="Логин вручную", max_length=64, required=False)
    expiration_date = forms.DateField(label="Срок действия учетной записи", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True).order_by("sort_order", "label")
        self.fields["branch"].choices = [(branch.key, branch.label) for branch in branches]


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ["key", "label", "ou_dn", "is_hq", "is_active", "sort_order"]
        labels = {"key": "Код", "label": "Название", "ou_dn": "OU DN", "is_hq": "Головной вуз", "is_active": "Активен", "sort_order": "Порядок сортировки"}


class AdManagedGroupForm(forms.ModelForm):
    class Meta:
        model = AdManagedGroup
        fields = ["code", "name", "dn", "is_active"]
        labels = {"code": "Код", "name": "Название группы", "dn": "DN группы", "is_active": "Активна"}


class DefaultAssignmentRuleForm(forms.ModelForm):
    class Meta:
        model = DefaultAssignmentRule
        fields = ["branch", "applies_to_gender", "group", "source", "priority", "is_active"]
        labels = {"branch": "Филиал", "applies_to_gender": "Пол", "group": "AD-группа", "source": "Источник", "priority": "Приоритет", "is_active": "Активно"}


class WebRoleForm(forms.Form):
    name = forms.CharField(label="Название роли", max_length=150)
    description = forms.CharField(label="Описание", max_length=255, required=False)
    permissions = forms.ModelMultipleChoiceField(label="Права", queryset=Permission.objects.order_by("content_type__app_label", "codename"), required=False, widget=forms.CheckboxSelectMultiple)


class WebUserAccessForm(forms.Form):
    user = forms.ModelChoiceField(label="Пользователь", queryset=User.objects.order_by("username"))
    groups = forms.ModelMultipleChoiceField(label="Роли", queryset=Group.objects.order_by("name"), required=False, widget=forms.CheckboxSelectMultiple)
    is_active = forms.BooleanField(label="Активен", required=False, initial=True)
    is_staff = forms.BooleanField(label="Доступ в Django admin", required=False)


class WebUserCreateForm(forms.Form):
    username = forms.CharField(label="Логин", max_length=150)
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    email = forms.EmailField(label="Email", required=False)
    groups = forms.ModelMultipleChoiceField(label="Роли", queryset=Group.objects.order_by("name"), required=False, widget=forms.CheckboxSelectMultiple)
    is_active = forms.BooleanField(label="Активен", required=False, initial=True)
    is_staff = forms.BooleanField(label="Доступ в Django admin", required=False)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует.")
        return username
