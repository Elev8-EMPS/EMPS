from django.urls import path

from . import views

urlpatterns = [
    path("security/setup-2fa/", views.setup_2fa, name="setup_2fa"),
    path("security/remove-2fa/", views.remove_2fa, name="remove_2fa"),
    path("security/regenerate-backup-codes/", views.regenerate_backup_codes, name="regenerate_backup_codes"),
]
