from django.urls import path

from . import views

urlpatterns = [
    path("calendar/", views.calendar_view, name="calendar"),
    path("calendar/request/", views.leave_request_create, name="leave_request_create"),
    path("calendar/my-requests/", views.my_leave_requests, name="my_leave_requests"),
    path("calendar/approvals/", views.leave_approvals, name="leave_approvals"),
    path("calendar/approvals/<int:pk>/decide/", views.leave_decide, name="leave_decide"),
    path("calendar/scope/", views.calendar_scope_edit, name="calendar_scope_edit"),
]
