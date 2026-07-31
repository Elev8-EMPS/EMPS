from django.contrib import admin

from .models import Organisation, Contact, Enquiry, Proposal


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "client_status", "vip_level", "tenant")
    list_filter = ("client_status", "tenant")
    search_fields = ("legal_name", "trading_name")


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("first_name", "last_name", "organisation", "email", "tenant")
    search_fields = ("first_name", "last_name", "email")


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("enquiry_number", "organisation", "status", "date_received", "tenant")
    list_filter = ("status", "tenant")


@admin.register(Proposal)
class ProposalAdmin(admin.ModelAdmin):
    list_display = ("proposal_number", "organisation", "status", "fee_amount", "tenant")
    list_filter = ("status", "tenant")
