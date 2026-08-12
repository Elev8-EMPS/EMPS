from django.urls import path

from . import views

urlpatterns = [
    path("projects/", views.project_list, name="project_list"),
    path("projects/new/", views.project_create, name="project_create"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("checklist-items/<int:pk>/toggle/", views.checklist_toggle, name="checklist_toggle"),
    path("stakeholders/<int:pk>/edit/", views.stakeholder_edit, name="stakeholder_edit"),
    path("milestones/", views.milestone_list, name="milestone_list"),
    path("milestones/new/", views.milestone_create, name="milestone_create"),
    path("milestones/<int:pk>/", views.milestone_detail, name="milestone_detail"),
    path("milestones/<int:pk>/edit/", views.milestone_edit, name="milestone_edit"),
    path("milestones/<int:pk>/duplicate/", views.milestone_duplicate, name="milestone_duplicate"),
    path("deadlines/due-reminders/", views.due_reminders, name="due_reminders"),
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/new/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("documents/", views.document_list, name="document_list"),
    path("documents/<int:pk>/", views.document_detail, name="document_detail"),
]
