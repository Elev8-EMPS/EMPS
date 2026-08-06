import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Creates (or updates) the deployment superusers used for admin access.

    The main admin account is created from environment variables so you can
    log into the admin without needing Shell access. A second fixed
    account, IDECRUY, is also created so there is a known master user for
    multi-tenant administration. The IDECRUY password can be overridden
    with IDECRUY_PASSWORD, or it falls back to the configured admin
    password if available.
    """

    help = "Create or update the deployment superusers"

    def _ensure_superuser(self, username, email, password):
        User = get_user_model()
        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        user.email = email or user.email
        user.is_staff = True
        user.is_superuser = True
        if password:
            user.set_password(password)
        user.save()
        return user, created

    def handle(self, *args, **options):
        admin_username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        admin_email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        admin_password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if admin_username and admin_password:
            self._ensure_superuser(admin_username, admin_email, admin_password)
            self.stdout.write(self.style.SUCCESS(f"Ensured superuser '{admin_username}'."))
        elif admin_username:
            self.stdout.write(
                self.style.WARNING(
                    "DJANGO_SUPERUSER_PASSWORD not set - skipping configured admin creation."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD not set - skipping configured admin creation."
                )
            )

        master_username = "IDECRUY"
        master_email = os.environ.get("IDECRUY_EMAIL", "")
        master_password = os.environ.get("IDECRUY_PASSWORD") or admin_password or "ChangeMe123!"

        user, created = self._ensure_superuser(master_username, master_email, master_password)
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created master superuser '{master_username}'."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated master superuser '{master_username}'."))
