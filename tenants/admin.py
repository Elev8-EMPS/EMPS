from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .admin_mixins import AuditedAdminMixin, TenantScopedAdmin
from .models import Tenant, UserProfile, Team, Modality, ChecklistItemTemplate


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")


@admin.register(Team)
class TeamAdmin(AuditedAdminMixin, TenantScopedAdmin, admin.ModelAdmin):
    list_display = ("name", "tenant")
    filter_horizontal = ("members", "modalities")


@admin.register(Modality)
class ModalityAdmin(AuditedAdminMixin, TenantScopedAdmin, admin.ModelAdmin):
    list_display = ("name", "code", "tenant")


@admin.register(ChecklistItemTemplate)
class ChecklistItemTemplateAdmin(AuditedAdminMixin, TenantScopedAdmin, admin.ModelAdmin):
    list_display = ("text", "modality", "always_included", "order", "tenant")
    list_filter = ("modality", "always_included", "tenant")


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    fk_name = "user"
    can_delete = False
    verbose_name_plural = "Tenant & role"


class TenantAwareUserAdmin(AuditedAdminMixin, UserAdmin):
    inlines = [UserProfileInline]


admin.site.unregister(User)
admin.site.register(User, TenantAwareUserAdmin)
