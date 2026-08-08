from django.core.management.base import BaseCommand

from calendar_app.services import process_approval_escalations
from tenants.models import Tenant


class Command(BaseCommand):
    help = "Raise in-app reminder/escalation tasks for stale leave and WFH approvals."

    def handle(self, *args, **options):
        total = 0
        for tenant in Tenant.objects.filter(is_active=True):
            total += process_approval_escalations(tenant)
        self.stdout.write(self.style.SUCCESS(f"Calendar approval processing complete; {total} task(s) created."))
