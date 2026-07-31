from django.urls import path

from . import views

urlpatterns = [
    path("organisations/", views.organisation_list, name="organisation_list"),
    path("organisations/<int:pk>/", views.organisation_detail, name="organisation_detail"),
]
