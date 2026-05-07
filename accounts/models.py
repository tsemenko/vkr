from django.contrib.auth.models import Group, User
from django.db import models


class ActionLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=64)
    target_login = models.CharField(max_length=128, blank=True, default="")
    success = models.BooleanField(default=False)
    details = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target_login}"


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
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES, default=SOURCE_LOCAL)
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
        gender = self.applies_to_gender or "ANY"
        return f"{self.branch.key}:{gender}:{self.group.name}"


class WebGroupRole(models.Model):
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name="web_role")
    is_system = models.BooleanField(default=False)
    description = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["group__name"]

    def __str__(self):
        return self.group.name
