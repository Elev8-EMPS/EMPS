from django.urls import path

from . import views

urlpatterns = [
    path("projects/", views.project_list, name="project_list"),
    path("projects/<int:pk>/", views.project_detail, name="project_detail"),
    path("milestones/", views.milestone_list, name="milestone_list"),
    path("milestones/<int:pk>/", views.milestone_detail, name="milestone_detail"),
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("documents/", views.document_list, name="document_list"),
    path("documents/<int:pk>/", views.document_detail, name="document_detail"),
]
