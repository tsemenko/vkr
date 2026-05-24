from django.contrib import admin

from .models import ActionLog, AdManagedGroup, Branch, DefaultAssignmentRule, SystemLog, WebGroupRole


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target_login", "success")
    list_filter = ("action", "success", "created_at")
    search_fields = ("target_login", "details", "actor__username")


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target", "success")
    list_filter = ("action", "success", "created_at")
    search_fields = ("target", "details", "actor__username")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "is_hq", "sort_order")
    list_filter = ("is_hq",)
    search_fields = ("key", "label", "ou_dn")


@admin.register(AdManagedGroup)
class AdManagedGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "dn")
    search_fields = ("code", "name", "dn")


@admin.register(DefaultAssignmentRule)
class DefaultAssignmentRuleAdmin(admin.ModelAdmin):
    list_display = ("branch", "group", "priority")
    search_fields = ("branch__label", "group__name", "group__dn")


@admin.register(WebGroupRole)
class WebGroupRoleAdmin(admin.ModelAdmin):
    list_display = ("display_name", "group", "description")
    search_fields = ("group__name", "description")
