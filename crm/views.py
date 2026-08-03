from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from tenants.utils import get_user_tenant
from .models import Organisation, Proposal, Enquiry


@login_required
def organisation_list(request):
    tenant = get_user_tenant(request)
    orgs = Organisation.objects.filter(tenant=tenant) if tenant else Organisation.objects.none()

    q = request.GET.get("q", "").strip()
    if q:
        orgs = orgs.filter(legal_name__icontains=q)

    orgs = orgs.order_by("legal_name")

    return render(request, "crm/organisation_list.html", {
        "active_nav": "organisations",
        "user_tenant": tenant,
        "organisations": orgs,
        "q": q,
    })


@login_required
def organisation_detail(request, pk):
    tenant = get_user_tenant(request)
    org = get_object_or_404(Organisation, pk=pk, tenant=tenant)

    tab = request.GET.get("tab", "overview")

    return render(request, "crm/organisation_detail.html", {
        "active_nav": "organisations",
        "user_tenant": tenant,
        "org": org,
        "tab": tab,
        "contacts": org.contacts.all() if tab == "contacts" else None,
        "enquiries": org.enquiries.all() if tab == "enquiries" else None,
        "proposals": org.proposals.all() if tab == "proposals" else None,
        "projects": org.projects.all() if tab == "projects" else None,
    })


@login_required
def proposal_list(request):
    tenant = get_user_tenant(request)
    proposals = Proposal.objects.filter(tenant=tenant) if tenant else Proposal.objects.none()

    q = request.GET.get("q", "").strip()
    if q:
        proposals = proposals.filter(proposal_number__icontains=q) | proposals.filter(
            organisation__legal_name__icontains=q
        )

    status = request.GET.get("status", "").strip()
    if status:
        proposals = proposals.filter(status=status)

    proposals = proposals.select_related("organisation").order_by("-issue_date", "proposal_number")

    return render(request, "crm/proposal_list.html", {
        "active_nav": "proposals",
        "user_tenant": tenant,
        "proposals": proposals,
        "q": q,
        "status": status,
        "status_choices": Proposal.STATUS_CHOICES,
    })


@login_required
def proposal_detail(request, pk):
    tenant = get_user_tenant(request)
    proposal = get_object_or_404(
        Proposal.objects.select_related("organisation", "contact", "enquiry", "director_approved_by"),
        pk=pk, tenant=tenant,
    )
    return render(request, "crm/proposal_detail.html", {
        "active_nav": "proposals",
        "user_tenant": tenant,
        "proposal": proposal,
    })


@login_required
def enquiry_list(request):
    tenant = get_user_tenant(request)
    enquiries = Enquiry.objects.filter(tenant=tenant) if tenant else Enquiry.objects.none()

    q = request.GET.get("q", "").strip()
    if q:
        enquiries = enquiries.filter(enquiry_number__icontains=q) | enquiries.filter(
            organisation__legal_name__icontains=q
        )

    status = request.GET.get("status", "").strip()
    if status:
        enquiries = enquiries.filter(status=status)

    enquiries = enquiries.select_related("organisation").order_by("-date_received", "enquiry_number")

    return render(request, "crm/enquiry_list.html", {
        "active_nav": "enquiries",
        "user_tenant": tenant,
        "enquiries": enquiries,
        "q": q,
        "status": status,
        "status_choices": Enquiry.STATUS_CHOICES,
    })


@login_required
def enquiry_detail(request, pk):
    tenant = get_user_tenant(request)
    enquiry = get_object_or_404(
        Enquiry.objects.select_related("organisation", "contact", "responsible_director"),
        pk=pk, tenant=tenant,
    )
    # Any proposal(s) already created from this enquiry
    proposals = Proposal.objects.filter(enquiry=enquiry)

    return render(request, "crm/enquiry_detail.html", {
        "active_nav": "enquiries",
        "user_tenant": tenant,
        "enquiry": enquiry,
        "proposals": proposals,
    })
