from django.contrib import admin

from .models import LeaveRequest, WFHDay, CalendarScope


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "leave_type", "start_date", "end_date", "status", "tenant")
    list_filter = ("status", "leave_type", "tenant")
    search_fields = ("user__username", "reason")


@admin.register(WFHDay)
class WFHDayAdmin(admin.ModelAdmin):
    list_display = ("user", "weekday", "tenant")
    list_filter = ("weekday", "tenant")


@admin.register(CalendarScope)
class CalendarScopeAdmin(admin.ModelAdmin):
    list_display = ("user",)
    filter_horizontal = ("included_teams",)
