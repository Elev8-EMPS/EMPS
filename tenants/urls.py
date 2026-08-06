from django.urls import path

from . import views

urlpatterns = [
    path("manage/", views.manage_hub, name="manage_hub"),
    path("manage/users/new/", views.manage_user_create, name="manage_user_create"),
    path("manage/users/<int:pk>/edit/", views.manage_user_edit, name="manage_user_edit"),
    path("manage/teams/new/", views.manage_team_create, name="manage_team_create"),
    path("manage/teams/<int:pk>/edit/", views.manage_team_edit, name="manage_team_edit"),
    path("manage/modalities/new/", views.manage_modality_create, name="manage_modality_create"),
    path("manage/modalities/<int:pk>/edit/", views.manage_modality_edit, name="manage_modality_edit"),
]
