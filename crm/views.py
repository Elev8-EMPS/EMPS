from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.utils import get_user_tenant
from .models import Organisation, Proposal, Enquiry, Communication


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


@login_required
def communication_list(request):
    tenant = get_user_tenant(request)
    comms = Communication.objects.filter(tenant=tenant) if tenant else Communication.objects.none()

    comm_type = request.GET.get("type", "").strip()
    if comm_type:
        comms = comms.filter(communication_type=comm_type)

    project_id = request.GET.get("project", "").strip()
    if project_id:
        comms = comms.filter(related_project_id=project_id)

    q = request.GET.get("q", "").strip()
    if q:
        comms = comms.filter(subject__icontains=q) | comms.filter(body__icontains=q)

    comms = comms.select_related("organisation", "related_project", "logged_by")

    from delivery.models import Project
    projects = Project.objects.filter(tenant=tenant).order_by("project_number") if tenant else Project.objects.none()

    return render(request, "crm/communication_list.html", {
        "active_nav": "communications",
        "user_tenant": tenant,
        "communications": comms,
        "q": q,
        "comm_type": comm_type,
        "project_id": project_id,
        "type_choices": Communication.TYPE_CHOICES,
        "projects": projects,
    })


@login_required
def communication_create(request):
    tenant = get_user_tenant(request)

    if request.method == "POST":
        occurred_at_raw = request.POST.get("occurred_at")
        if occurred_at_raw:
            naive = timezone.datetime.fromisoformat(occurred_at_raw)
            occurred_at = timezone.make_aware(naive) if timezone.is_naive(naive) else naive
        else:
            occurred_at = timezone.now()
        comm = Communication(
            tenant=tenant,
            logged_by=request.user,
            communication_type=request.POST.get("communication_type", "note"),
            direction=request.POST.get("direction", ""),
            subject=request.POST.get("subject", "").strip(),
            body=request.POST.get("body", "").strip(),
            sender=request.POST.get("sender", "").strip(),
            recipients=request.POST.get("recipients", "").strip(),
            occurred_at=occurred_at,
        )
        org_id = request.POST.get("organisation")
        if org_id:
            comm.organisation_id = org_id
        contact_id = request.POST.get("contact")
        if contact_id:
            comm.contact_id = contact_id
        project_id = request.POST.get("related_project")
        if project_id:
            comm.related_project_id = project_id

        if comm.body or comm.subject:
            comm.save()
            return redirect("communication_detail", pk=comm.pk)

    from delivery.models import Project
    organisations = Organisation.objects.filter(tenant=tenant).order_by("legal_name") if tenant else Organisation.objects.none()
    projects = Project.objects.filter(tenant=tenant).order_by("project_number") if tenant else Project.objects.none()

    preselect_project = request.GET.get("project", "")

    return render(request, "crm/communication_create.html", {
        "active_nav": "communications",
        "user_tenant": tenant,
        "organisations": organisations,
        "projects": projects,
        "type_choices": Communication.TYPE_CHOICES,
        "direction_choices": Communication.DIRECTION_CHOICES,
        "preselect_project": preselect_project,
        "now": timezone.now(),
    })


@login_required
def communication_detail(request, pk):
    tenant = get_user_tenant(request)
    comm = get_object_or_404(
        Communication.objects.select_related("organisation", "contact", "related_project", "logged_by"),
        pk=pk, tenant=tenant,
    )
    return render(request, "crm/communication_detail.html", {
        "active_nav": "communications",
        "user_tenant": tenant,
        "comm": comm,
    })
