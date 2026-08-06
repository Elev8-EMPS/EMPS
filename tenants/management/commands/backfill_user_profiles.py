from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from tenants.models import Tenant, UserProfile


class Command(BaseCommand):
    help = "Create missing tenant profiles for existing users and assign them to a tenant if possible."

    def handle(self, *args, **options):
        User = get_user_model()
        tenant = Tenant.objects.order_by("pk").first()
        if tenant is None:
            tenant = Tenant.objects.create(name="Default Tenant")
            self.stdout.write(self.style.WARNING("No tenant was found, so I created a default tenant."))

        users_without_profile = User.objects.filter(profile__isnull=True)
        created_count = 0
        for user in users_without_profile:
            profile = UserProfile.objects.create(user=user)
            profile.tenant = tenant
            profile.save()
            created_count += 1

        if created_count:
            self.stdout.write(self.style.SUCCESS(f"Backfilled {created_count} user profile(s) for tenant '{tenant.name}'."))
        else:
            self.stdout.write(self.style.SUCCESS("All existing users already had profiles."))
