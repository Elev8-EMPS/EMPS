from django.urls import path

from . import views

urlpatterns = [
    path("calendar/", views.calendar_home, name="calendar_home"),
    path("calendar/leave/new/", views.leave_request_create, name="leave_request_create"),
    path("calendar/wfh/new/", views.wfh_request_create, name="wfh_request_create"),
    path("calendar/wfh/", views.wfh_schedule, name="wfh_schedule"),
    path("calendar/wfh/<int:user_id>/", views.wfh_schedule, name="wfh_schedule_user"),
    path("calendar/requests/", views.my_requests, name="my_requests"),
    path("calendar/preferences/", views.calendar_preferences, name="calendar_preferences"),
    path("calendar/approvals/", views.leave_approval_list, name="leave_approval_list"),
    path("calendar/approvals/leave/<int:pk>/", views.leave_approve, name="leave_approve"),
    path("calendar/approvals/wfh/<int:pk>/", views.wfh_approve, name="wfh_approve"),
    path("management/", views.management_hub, name="management_hub"),
    path("management/calendar-config/", views.calendar_configuration, name="calendar_configuration"),
]
