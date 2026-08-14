from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.utils import get_user_tenant, can_view_proposals, get_dashboard_visibility
from .models import Organisation, Proposal, Enquiry, Communication, Contact


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

    proposals = None
    proposals_restricted = False
    if tab == "proposals":
        if can_view_proposals(request.user):
            proposals = org.proposals.all()
        elif get_dashboard_visibility(tenant) == "responsible_for" and org.relationship_owner_id == request.user.id:
            proposals = org.proposals.all()
        else:
            proposals_restricted = True

    return render(request, "crm/organisation_detail.html", {
        "active_nav": "organisations",
        "user_tenant": tenant,
        "org": org,
        "tab": tab,
        "contacts": org.contacts.all() if tab == "contacts" else None,
        "enquiries": org.enquiries.all() if tab == "enquiries" else None,
        "proposals": proposals,
        "proposals_restricted": proposals_restricted,
        "projects": org.projects.all() if tab == "projects" else None,
    })


@login_required
def proposal_list(request):
    tenant = get_user_tenant(request)
    proposals = Proposal.objects.filter(tenant=tenant) if tenant else Proposal.objects.none()

    full_access = can_view_proposals(request.user)
    responsible_only = False

    if not full_access:
        if get_dashboard_visibility(tenant) == "responsible_for":
            responsible_only = True
            proposals = proposals.filter(
                Q(enquiry__responsible_director=request.user)
                | Q(organisation__relationship_owner=request.user)
                | Q(director_approved_by=request.user)
            ).distinct()
        else:
            messages.error(request, "You don't have permission to view Fee Proposals.")
            return redirect("command_centre")

    q = request.GET.get("q", "").strip()
    if q:
        proposals = proposals.filter(proposal_number__icontains=q) | proposals.filter(
            organisation__legal_name__icontains=q
        )

    status = request.GET.get("status", "").strip()
    if status:
        proposals = proposals.filter(status__in=status.split(","))

    today = timezone.localtime(timezone.now()).date()
    followup = request.GET.get("followup", "").strip()
    if followup == "due":
        proposals = proposals.filter(follow_up_date__lte=today).filter(status__in=[
            "draft", "internal_review", "director_review", "approved", "issued", "follow_up_due", "revised"
        ])
    elif followup == "scheduled":
        proposals = proposals.filter(follow_ups__status="scheduled", follow_ups__due_date__gte=today).distinct()

    proposals = proposals.select_related("organisation").order_by("-issue_date", "proposal_number")

    return render(request, "crm/proposal_list.html", {
        "active_nav": "proposals",
        "user_tenant": tenant,
        "proposals": proposals,
        "q": q,
        "status": status,
        "status_choices": Proposal.STATUS_CHOICES,
        "full_access": full_access,
        "responsible_only": responsible_only,
    })


@login_required
def proposal_detail(request, pk):
    tenant = get_user_tenant(request)
    proposal = get_object_or_404(
        Proposal.objects.select_related("organisation", "contact", "enquiry", "director_approved_by"),
        pk=pk, tenant=tenant,
    )

    full_access = can_view_proposals(request.user)
    is_responsible_for_this_one = (
        proposal.director_approved_by_id == request.user.id
        or (proposal.enquiry_id and proposal.enquiry.responsible_director_id == request.user.id)
        or proposal.organisation.relationship_owner_id == request.user.id
    )

    if not full_access:
        if not (get_dashboard_visibility(tenant) == "responsible_for" and is_responsible_for_this_one):
            messages.error(request, "You don't have permission to view this proposal.")
            return redirect("command_centre")

    if request.method == "POST" and request.POST.get("action") == "action_followup":
        if not full_access:
            messages.error(request, "You don't have permission to action proposal follow-ups.")
            return redirect("proposal_detail", pk=proposal.pk)
        from .models import ProposalFollowUp, add_working_days
        followup_id = request.POST.get("followup_id")
        followup = get_object_or_404(ProposalFollowUp, pk=followup_id, proposal=proposal, tenant=tenant)
        followup.outcome = request.POST.get("outcome", "")
        followup.outcome_notes = request.POST.get("outcome_notes", "").strip()
        followup.status = "done"
        followup.actioned_by = request.user
        followup.actioned_at = timezone.now()
        followup.save()

        terminal_statuses = ["accepted", "declined", "lost", "withdrawn", "expired"]
        if proposal.status not in terminal_statuses:
            ProposalFollowUp.objects.create(
                tenant=tenant, proposal=proposal, follow_up_number=followup.follow_up_number + 1,
                due_date=add_working_days(timezone.now().date(), 7),
            )
        return redirect("proposal_detail", pk=proposal.pk)

    return render(request, "crm/proposal_detail.html", {
        "active_nav": "proposals",
        "user_tenant": tenant,
        "proposal": proposal,
        "follow_ups": proposal.follow_ups.all() if full_access else proposal.follow_ups.none(),
        "full_access": full_access,
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


@login_required
def contact_list(request):
    tenant = get_user_tenant(request)
    if not tenant:
        return render(request, "crm/contact_list.html", {
            "active_nav": "contacts", "user_tenant": tenant, "org_groups": [], "unaffiliated": [],
            "q": "", "org_id": "", "organisations": Organisation.objects.none(),
        })

    q = request.GET.get("q", "").strip()
    org_id = request.GET.get("organisation", "").strip()

    # Which organisations are "in scope" - either directly matched by name,
    # or the employer of a contact matched by name/email/mobile. Either way,
    # we then show that organisation's FULL contact list, not just the hit.
    org_ids = set()
    if org_id:
        org_ids.add(int(org_id))
    elif q:
        org_ids.update(
            Organisation.objects.filter(tenant=tenant, legal_name__icontains=q).values_list("id", flat=True)
        )
        org_ids.update(
            Contact.objects.filter(tenant=tenant, organisation__isnull=False)
            .filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q) |
                Q(email__icontains=q) | Q(mobile__icontains=q)
            )
            .values_list("organisation_id", flat=True)
        )
    else:
        org_ids.update(Organisation.objects.filter(tenant=tenant).values_list("id", flat=True))

    organisations = Organisation.objects.filter(tenant=tenant, id__in=org_ids).order_by("legal_name")
    org_groups = [
        {"organisation": org, "contacts": org.contacts.order_by("first_name", "last_name")}
        for org in organisations
    ]

    # Contacts with no organisation at all, matched by search (or shown when browsing everything)
    unaffiliated_qs = Contact.objects.filter(tenant=tenant, organisation__isnull=True)
    if q and not org_id:
        unaffiliated_qs = unaffiliated_qs.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) |
            Q(email__icontains=q) | Q(mobile__icontains=q)
        )
    elif org_id:
        unaffiliated_qs = Contact.objects.none()
    unaffiliated = unaffiliated_qs.order_by("first_name", "last_name")

    return render(request, "crm/contact_list.html", {
        "active_nav": "contacts",
        "user_tenant": tenant,
        "org_groups": org_groups,
        "unaffiliated": unaffiliated,
        "q": q,
        "org_id": org_id,
        "organisations": Organisation.objects.filter(tenant=tenant).order_by("legal_name"),
    })


@login_required
def contact_detail(request, pk):
    tenant = get_user_tenant(request)
    contact = get_object_or_404(Contact.objects.select_related("organisation"), pk=pk, tenant=tenant)
    return render(request, "crm/contact_detail.html", {
        "active_nav": "organisations",
        "user_tenant": tenant,
        "contact": contact,
        "project_roles": contact.project_stakeholder_roles.select_related("project").order_by("-project__start_date"),
    })
