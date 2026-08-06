from django.core.management.base import BaseCommand

from tenants.models import Tenant, UserProfile


class Command(BaseCommand):
    """
    One-time (but safe to re-run) backfill: every UserProfile with no
    tenant set gets assigned to the tenant, so users created before
    the Manage area existed (via Django admin, or the superuser from
    create_admin) actually show up in Manage -> Users instead of
    being invisible there.

    Only acts while there's exactly one tenant - once a second tenant
    exists, silently guessing which one a user belongs to is no
    longer safe, so this becomes a no-op and assignment has to be
    done by hand from then on.
    """

    help = "Assign existing tenant-less users to the tenant, so they appear in Manage"

    def handle(self, *args, **options):
        if Tenant.objects.count() != 1:
            self.stdout.write(
                "Skipping - this only runs automatically while there's exactly one tenant."
            )
            return

        tenant = Tenant.objects.first()
        candidates = UserProfile.objects.filter(tenant__isnull=True)
        count = candidates.count()

        if not count:
            self.stdout.write("No tenant-less users to backfill.")
            return

        candidates.update(tenant=tenant)
        self.stdout.write(self.style.SUCCESS(f"Assigned {count} user(s) to '{tenant.name}'."))
