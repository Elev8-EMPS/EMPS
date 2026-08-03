from django.urls import path

from . import views

urlpatterns = [
    path("organisations/", views.organisation_list, name="organisation_list"),
    path("organisations/<int:pk>/", views.organisation_detail, name="organisation_detail"),
    path("enquiries/", views.enquiry_list, name="enquiry_list"),
    path("enquiries/<int:pk>/", views.enquiry_detail, name="enquiry_detail"),
    path("proposals/", views.proposal_list, name="proposal_list"),
    path("proposals/<int:pk>/", views.proposal_detail, name="proposal_detail"),
]
