from django.core.management.base import BaseCommand

from delivery.models import ProjectStakeholder
from delivery.views import _find_or_create_contact_from_external


class Command(BaseCommand):
    """
    One-time (but safe to re-run) backfill: any ProjectStakeholder
    that still only has the old external_name/company/email/phone
    fields (from before contacts were auto-created) gets a real
    Contact record created/matched and linked, exactly the same way
    new stakeholders are handled now. Safe to run on every deploy -
    it only ever touches rows that still have no linked contact, so
    once everything's backfilled it does nothing.
    """

    help = "Backfill real Contact records for stakeholders that predate contact auto-creation"

    def handle(self, *args, **options):
        candidates = ProjectStakeholder.objects.filter(contact__isnull=True).exclude(external_name="")
        if not candidates.exists():
            self.stdout.write("No stakeholders need backfilling.")
            return

        fixed = 0
        for stakeholder in candidates:
            contact = _find_or_create_contact_from_external(
                stakeholder.tenant, stakeholder.external_name, stakeholder.external_company,
                stakeholder.external_email, stakeholder.external_phone,
            )
            if contact:
                stakeholder.contact = contact
                stakeholder.save(update_fields=["contact"])
                fixed += 1

        self.stdout.write(self.style.SUCCESS(f"Backfilled {fixed} stakeholder(s) with real contacts."))
