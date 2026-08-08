from django import forms
from django.core.exceptions import ValidationError

from .models import CalendarEventType, CalendarPreference, CalendarSettings, LeaveRequest, LeaveType, WFHChangeRequest, WFHSchedule


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ["leave_type", "start_date", "end_date", "start_part", "end_part", "reason"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields["leave_type"].queryset = LeaveType.objects.filter(tenant=tenant, is_active=True)

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        start_part = cleaned.get("start_part")
        end_part = cleaned.get("end_part")
        if start and end and end < start:
            raise ValidationError("The end date cannot be before the start date.")
        if start and end:
            weekdays = sum(1 for i in range((end - start).days + 1) if (start + __import__("datetime").timedelta(days=i)).weekday() < 5)
            if weekdays == 0:
                raise ValidationError("Leave must include at least one working day.")
        if start and end and start == end:
            if start_part == "full" and end_part != "full":
                raise ValidationError("For a single day, choose Full day or one half-day.")
            if start_part != "full" and end_part != "full" and start_part != end_part:
                raise ValidationError("For a single day, choose either morning or afternoon.")
            if start_part != "full" and end_part == "full":
                cleaned["end_part"] = start_part
        return cleaned


class WFHChangeRequestForm(forms.ModelForm):
    class Meta:
        model = WFHChangeRequest
        fields = ["change_type", "original_date", "requested_date", "reason"]
        widgets = {
            "original_date": forms.DateInput(attrs={"type": "date"}),
            "requested_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 3}),
        }


class CalendarPreferenceForm(forms.ModelForm):
    class Meta:
        model = CalendarPreference
        fields = ["show_leave", "show_wfh", "show_deadlines", "show_tasks", "show_followups", "show_projects", "show_fee_proposals", "show_company_wide"]


class WFHScheduleForm(forms.ModelForm):
    class Meta:
        model = WFHSchedule
        fields = ["monday", "tuesday", "wednesday", "thursday", "friday", "effective_from", "effective_to"]
        widgets = {
            "effective_from": forms.DateInput(attrs={"type": "date"}),
            "effective_to": forms.DateInput(attrs={"type": "date"}),
        }

class CalendarEventTypeForm(forms.ModelForm):
    class Meta:
        model = CalendarEventType
        fields = ["name", "colour", "text_colour", "is_active", "order"]


class LeaveTypeConfigForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = ["name", "colour", "counts_toward_leave", "requires_reason", "is_active", "order"]


class CalendarSettingsForm(forms.ModelForm):
    class Meta:
        model = CalendarSettings
        fields = ["reminder_after_business_days", "escalation_after_business_days", "allow_company_admin_override"]
