from django.contrib.auth.models import Group, User
from django.db import models


WEB_ROLE_SUPER_ADMIN = "AD Super Admins"
WEB_ROLE_OPERATOR = "AD Operators"
WEB_ROLE_NAMES = (WEB_ROLE_SUPER_ADMIN, WEB_ROLE_OPERATOR)
WEB_ROLE_LABELS = {
    WEB_ROLE_SUPER_ADMIN: "Супер-админ",
    WEB_ROLE_OPERATOR: "Оператор",
}

SYSTEM_SECTION_CHOICES = [
    ("monitoring", "Мониторинг"),
    ("create_user", "Создание учетной записи"),
    ("logs", "Журнал"),
    ("branches", "Филиалы"),
    ("groups", "AD-группы"),
    ("rules", "Правила"),
    ("roles", "Роли"),
    ("users", "Создание пользователя"),
]
SYSTEM_SECTION_LABELS = dict(SYSTEM_SECTION_CHOICES)


class ActionLog(models.Model):
    ACTION_CREATE_USER = "create_user"
    ACTION_UNLOCK_USER = "unlock_user"
    AD_ACTIONS = (ACTION_CREATE_USER, ACTION_UNLOCK_USER)
    ACTION_LABELS = {
        ACTION_CREATE_USER: "Создание пользователя",
        ACTION_UNLOCK_USER: "Разблокировка пользователя",
    }

    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=64)
    target_login = models.CharField(max_length=128, blank=True, default="")
    success = models.BooleanField(default=False)
    details = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    @property
    def action_label(self) -> str:
        return self.ACTION_LABELS.get(self.action, self.action)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target_login}"


class SystemLog(models.Model):
    ACTION_CREATE_BRANCH = "system_create_branch"
    ACTION_DELETE_BRANCH = "system_delete_branch"
    ACTION_CREATE_AD_GROUP = "system_create_ad_group"
    ACTION_DELETE_AD_GROUP = "system_delete_ad_group"
    ACTION_CREATE_RULE = "system_create_rule"
    ACTION_DELETE_RULE = "system_delete_rule"
    ACTION_UPDATE_WEB_ACCESS = "system_update_web_access"
    ACTION_CREATE_WEB_USER = "system_create_web_user"
    ACTION_DELETE_WEB_USER = "system_delete_web_user"
    ACTION_UPSERT_ROLE = "system_upsert_role"
    ACTION_DELETE_ROLE = "system_delete_role"

    ACTION_LABELS = {
        ACTION_CREATE_BRANCH: "Добавление филиала",
        ACTION_DELETE_BRANCH: "Удаление филиала",
        ACTION_CREATE_AD_GROUP: "Добавление AD-группы",
        ACTION_DELETE_AD_GROUP: "Удаление AD-группы",
        ACTION_CREATE_RULE: "Добавление правила",
        ACTION_DELETE_RULE: "Удаление правила",
        ACTION_UPDATE_WEB_ACCESS: "Назначение роли",
        ACTION_CREATE_WEB_USER: "Создание пользователя веб-сервиса",
        ACTION_DELETE_WEB_USER: "Удаление пользователя веб-сервиса",
        ACTION_UPSERT_ROLE: "Создание или изменение роли",
        ACTION_DELETE_ROLE: "Удаление роли",
    }

    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=64)
    target = models.CharField(max_length=150, blank=True, default="")
    success = models.BooleanField(default=True)
    details = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    @property
    def action_label(self) -> str:
        return self.ACTION_LABELS.get(self.action, self.action)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target}"


class Branch(models.Model):
    key = models.SlugField(max_length=32, unique=True)
    label = models.CharField(max_length=128)
    ou_dn = models.CharField(max_length=512)
    is_hq = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ["sort_order", "label"]

    def __str__(self):
        return self.label


class AdManagedGroup(models.Model):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=256)
    dn = models.CharField(max_length=512, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    @property
    def ad_identity(self) -> str:
        """DN или sAMAccountName, который можно передавать в Add-ADGroupMember."""
        return (self.dn or self.name or self.code).strip()

    def __str__(self):
        return self.name


class DefaultAssignmentRule(models.Model):
    SOURCE_LOCAL = "local"
    SOURCE_AD = "ad"
    SOURCE_CHOICES = [
        (SOURCE_LOCAL, "Локально"),
        (SOURCE_AD, "Из AD"),
    ]

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="default_rules")
    applies_to_gender = models.CharField(max_length=1, blank=True, default="")
    group = models.ForeignKey(AdManagedGroup, on_delete=models.CASCADE, related_name="default_rules")
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_AD)
    priority = models.IntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "applies_to_gender", "group"],
                name="uniq_default_rule_branch_gender_group",
            )
        ]

    def __str__(self):
        return f"{self.branch.key}:{self.group.name}"


class WebGroupRole(models.Model):
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="web_role")
    is_system = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True, default="")
    allowed_sections = models.JSONField(default=list, blank=True)
    allowed_branches = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["group__name"]

    @property
    def display_name(self) -> str:
        return WEB_ROLE_LABELS.get(self.group.name, self.group.name)

    def allowed_section_labels(self) -> list[str]:
        return [SYSTEM_SECTION_LABELS.get(section, section) for section in (self.allowed_sections or [])]

    def allowed_branch_labels(self) -> list[str]:
        branches = Branch.objects.filter(key__in=(self.allowed_branches or [])).order_by("sort_order", "label")
        labels_by_key = {branch.key: branch.label for branch in branches}
        return [labels_by_key.get(branch_key, branch_key) for branch_key in (self.allowed_branches or [])]

    def __str__(self):
        return self.display_name


class WebUserPasswordState(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="password_state")
    must_change_password = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username"]

    def __str__(self):
        status = "требуется смена пароля" if self.must_change_password else "пароль изменен"
        return f"{self.user.username}: {status}"
