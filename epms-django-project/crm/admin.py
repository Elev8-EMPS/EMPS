from django.contrib import admin

from tenants.admin_mixins import ExportCsvMixin, TenantScopedAdmin
from .models import Organisation, Contact, Enquiry, Proposal, Communication, ProposalFollowUp


@admin.register(Organisation)
class OrganisationAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("legal_name", "client_status", "vip_level", "industry", "relationship_owner", "last_contact", "tenant")
    list_filter = ("client_status", "vip_level", "industry", "is_active", "tenant")
    search_fields = ("legal_name", "trading_name", "email", "phone")
    date_hierarchy = "client_since"


@admin.register(Contact)
class ContactAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("first_name", "last_name", "organisation", "email", "mobile", "is_active", "tenant")
    list_filter = ("is_active", "is_proposal_recipient", "is_invoice_recipient", "tenant")
    search_fields = ("first_name", "last_name", "email", "mobile")


@admin.register(Enquiry)
class EnquiryAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("enquiry_number", "organisation", "status", "responsible_director", "date_received", "proposal_due_date", "tenant")
    list_filter = ("status", "source", "tenant")
    search_fields = ("enquiry_number", "organisation__legal_name", "description")
    date_hierarchy = "date_received"


@admin.register(Proposal)
class ProposalAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("proposal_number", "organisation", "status", "fee_amount", "issue_date", "follow_up_date", "tenant")
    list_filter = ("status", "tenant")
    search_fields = ("proposal_number", "organisation__legal_name")
    date_hierarchy = "issue_date"


@admin.register(Communication)
class CommunicationAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("subject", "communication_type", "direction", "related_project", "organisation", "occurred_at", "logged_by", "tenant")
    list_filter = ("communication_type", "direction", "tenant")
    search_fields = ("subject", "body", "organisation__legal_name")
    date_hierarchy = "occurred_at"

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.logged_by:
            obj.logged_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ProposalFollowUp)
class ProposalFollowUpAdmin(TenantScopedAdmin, admin.ModelAdmin):
    list_display = ("proposal", "follow_up_number", "due_date", "status", "outcome", "tenant")
    list_filter = ("status", "outcome", "tenant")
