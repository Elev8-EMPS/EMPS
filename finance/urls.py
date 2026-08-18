from django.urls import path

from . import views

urlpatterns = [
    path("invoices/", views.invoice_list, name="invoice_list"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("milestones/<int:milestone_pk>/invoice/new/", views.invoice_create, name="invoice_create"),
    path("finance/wip/", views.wip_dashboard, name="wip_dashboard"),
]
