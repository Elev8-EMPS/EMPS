from django.contrib import admin

from tenants.admin_mixins import ExportCsvMixin, TenantScopedAdmin
from .models import Organisation, Contact, Enquiry, Proposal


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
