from django.contrib import admin

from tenants.admin_mixins import AuditedAdminMixin
from .models import LeaveRequest, WFHDay, CalendarScope


@admin.register(LeaveRequest)
class LeaveRequestAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("user", "leave_type", "start_date", "end_date", "status", "tenant")
    list_filter = ("status", "leave_type", "tenant")
    search_fields = ("user__username", "reason")


@admin.register(WFHDay)
class WFHDayAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("user", "weekday", "tenant")
    list_filter = ("weekday", "tenant")


@admin.register(CalendarScope)
class CalendarScopeAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("user",)
    filter_horizontal = ("included_teams",)
