from django.contrib import admin

from .models import ActionLog, AdManagedGroup, Branch, DefaultAssignmentRule, WebGroupRole


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target_login", "success")
    list_filter = ("action", "success", "created_at")
    search_fields = ("target_login", "details", "actor__username")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "is_hq", "is_active", "sort_order")
    list_filter = ("is_hq", "is_active")
    search_fields = ("key", "label", "ou_dn")


@admin.register(AdManagedGroup)
class AdManagedGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "dn")


@admin.register(DefaultAssignmentRule)
class DefaultAssignmentRuleAdmin(admin.ModelAdmin):
    list_display = ("branch", "applies_to_gender", "group", "source", "priority", "is_active")
    list_filter = ("source", "is_active", "applies_to_gender")
    search_fields = ("branch__label", "group__name")


@admin.register(WebGroupRole)
class WebGroupRoleAdmin(admin.ModelAdmin):
    list_display = ("group", "is_system", "description")
    list_filter = ("is_system",)
    search_fields = ("group__name", "description")
