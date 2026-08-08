from django.contrib import admin

from .models import CalendarEventType, CalendarPreference, CalendarSettings, LeaveApproval, LeaveRequest, LeaveType, PublicHoliday, WFHChangeRequest, WFHSchedule


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "tenant", "counts_toward_leave", "requires_reason", "is_active")
    list_filter = ("tenant", "is_active", "counts_toward_leave")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("requester", "leave_type", "start_date", "end_date", "working_days", "status", "current_approver")
    list_filter = ("tenant", "status", "leave_type")
    readonly_fields = ("submitted_at", "decided_at", "last_reminder_at", "escalated_at")


@admin.register(LeaveApproval)
class LeaveApprovalAdmin(admin.ModelAdmin):
    list_display = ("request", "approver", "action", "acted_at")
    list_filter = ("tenant", "action")
    readonly_fields = ("acted_at",)


@admin.register(WFHSchedule)
class WFHScheduleAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "monday", "tuesday", "wednesday", "thursday", "friday")
    list_filter = ("tenant",)


@admin.register(WFHChangeRequest)
class WFHChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("requester", "change_type", "original_date", "requested_date", "status", "current_approver")
    list_filter = ("tenant", "status", "change_type")


@admin.register(CalendarPreference)
class CalendarPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "show_leave", "show_wfh", "show_deadlines", "show_tasks")
    list_filter = ("tenant",)


@admin.register(CalendarEventType)
class CalendarEventTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "colour", "tenant", "is_active", "order")
    list_filter = ("tenant", "is_active")


@admin.register(CalendarSettings)
class CalendarSettingsAdmin(admin.ModelAdmin):
    list_display = ("tenant", "reminder_after_business_days", "escalation_after_business_days", "allow_company_admin_override")


@admin.register(PublicHoliday)
class PublicHolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name", "tenant")
    list_filter = ("tenant",)
