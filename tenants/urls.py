from django.urls import path

from . import views

urlpatterns = [
    path("manage/", views.manage_home, name="manage_home"),

    path("manage/users/", views.manage_user_list, name="manage_user_list"),
    path("manage/users/new/", views.manage_user_create, name="manage_user_create"),
    path("manage/users/<int:pk>/", views.manage_user_edit, name="manage_user_edit"),

    path("manage/teams/", views.manage_team_list, name="manage_team_list"),
    path("manage/teams/new/", views.manage_team_create, name="manage_team_create"),
    path("manage/teams/<int:pk>/", views.manage_team_edit, name="manage_team_edit"),

    path("manage/modalities/", views.manage_modality_list, name="manage_modality_list"),
    path("manage/modalities/new/", views.manage_modality_create, name="manage_modality_create"),
    path("manage/modalities/<int:pk>/", views.manage_modality_edit, name="manage_modality_edit"),
]
