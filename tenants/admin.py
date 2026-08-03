from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .admin_mixins import TenantScopedAdmin
from .models import Tenant, UserProfile, Team


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")


@admin.register(Team)
class TeamAdmin(TenantScopedAdmin, admin.ModelAdmin):
    list_display = ("name", "tenant")
    filter_horizontal = ("members",)


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Tenant assignment"


class TenantAwareUserAdmin(UserAdmin):
    inlines = [UserProfileInline]


admin.site.unregister(User)
admin.site.register(User, TenantAwareUserAdmin)
