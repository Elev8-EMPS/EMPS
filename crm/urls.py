from django.urls import path

from . import views

urlpatterns = [
    path("organisations/", views.organisation_list, name="organisation_list"),
    path("organisations/<int:pk>/", views.organisation_detail, name="organisation_detail"),
    path("organisations/<int:pk>/edit/", views.organisation_edit, name="organisation_edit"),
    path("contacts/", views.contact_list, name="contact_list"),
    path("contacts/<int:pk>/", views.contact_detail, name="contact_detail"),
    path("contacts/<int:pk>/edit/", views.contact_edit, name="contact_edit"),
    path("enquiries/", views.enquiry_list, name="enquiry_list"),
    path("enquiries/<int:pk>/", views.enquiry_detail, name="enquiry_detail"),
    path("proposals/", views.proposal_list, name="proposal_list"),
    path("proposals/<int:pk>/", views.proposal_detail, name="proposal_detail"),
    path("communications/", views.communication_list, name="communication_list"),
    path("communications/new/", views.communication_create, name="communication_create"),
    path("communications/<int:pk>/", views.communication_detail, name="communication_detail"),
]
