import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Creates (or updates the password of) a superuser from environment
    variables, so you can log into the admin without needing Shell
    access - useful on Render's free tier, which doesn't include it.

    Reads: DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL,
           DJANGO_SUPERUSER_PASSWORD

    Safe to run on every deploy: if the user already exists, it just
    updates the password rather than failing.
    """

    help = "Create or update the admin superuser from environment variables"

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    "DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD "
                    "not set - skipping admin creation."
                )
            )
            return

        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        user.email = email or user.email
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated superuser '{username}'."))
