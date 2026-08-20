from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from django.contrib.auth.models import User

from tenants.utils import get_user_tenant, can_view_proposals, can_edit_proposals, get_dashboard_visibility, diff_and_log_update
from tenants.models import Modality, log_audit
from .models import (
    Organisation, Proposal, Enquiry, Communication, Contact,
    FPScopeItem, FPExclusionItem, FPTermClause, FPPaymentTermOption, ProposalFeeLine,
)

ORGANISATION_EDITABLE_FIELDS = [
    "legal_name", "trading_name", "registration_number", "organisation_type", "industry",
    "website", "phone", "email", "address", "client_status", "vip_level",
    "relationship_owner_id", "client_since", "notes",
]
CONTACT_EDITABLE_FIELDS = [
    "first_name", "last_name", "job_title", "email", "mobile", "office_phone",
    "is_proposal_recipient", "is_invoice_recipient", "notes",
]


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
def organisation_edit(request, pk):
    tenant = get_user_tenant(request)
    org = get_object_or_404(Organisation, pk=pk, tenant=tenant)

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "You must give a reason for this change.")
            return redirect("organisation_edit", pk=org.pk)

        before = {f: getattr(org, f) for f in ORGANISATION_EDITABLE_FIELDS}

        org.legal_name = request.POST.get("legal_name", org.legal_name).strip()
        org.trading_name = request.POST.get("trading_name", "").strip()
        org.registration_number = request.POST.get("registration_number", "").strip()
        org.organisation_type = request.POST.get("organisation_type", "").strip()
        org.industry = request.POST.get("industry", "").strip()
        org.website = request.POST.get("website", "").strip()
        org.phone = request.POST.get("phone", "").strip()
        org.email = request.POST.get("email", "").strip()
        org.address = request.POST.get("address", "").strip()
        org.client_status = request.POST.get("client_status", org.client_status)
        org.vip_level = request.POST.get("vip_level", "").strip()
        org.relationship_owner_id = request.POST.get("relationship_owner") or None
        org.client_since = request.POST.get("client_since") or None
        org.notes = request.POST.get("notes", "").strip()
        org.save()

        changed = diff_and_log_update(request.user, tenant, org, before, reason)
        if changed:
            messages.success(request, "Organisation updated.")
        else:
            messages.success(request, "No changes were made.")
        return redirect("organisation_detail", pk=org.pk)

    return render(request, "crm/organisation_edit.html", {
        "active_nav": "organisations",
        "user_tenant": tenant,
        "org": org,
        "client_status_choices": Organisation.CLIENT_STATUS_CHOICES,
        "all_users": User.objects.filter(profile__tenant=tenant, is_active=True).order_by("username"),
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
def proposal_create(request, enquiry_pk=None):
    tenant = get_user_tenant(request)
    if not can_edit_proposals(request.user):
        messages.error(request, "You don't have permission to create Fee Proposals.")
        return redirect("command_centre")

    enquiry = None
    if enquiry_pk:
        enquiry = get_object_or_404(Enquiry, pk=enquiry_pk, tenant=tenant)

    if request.method == "POST":
        org_id = request.POST.get("organisation") or (enquiry.organisation_id if enquiry else None)
        if not org_id:
            messages.error(request, "Select a client organisation.")
            return redirect(request.path)

        number = f"FP-{Proposal.objects.filter(tenant=tenant).count() + 1:04d}"
        while Proposal.objects.filter(proposal_number=number).exists():
            number += "X"

        proposal = Proposal.objects.create(
            tenant=tenant, proposal_number=number, organisation_id=org_id,
            contact_id=request.POST.get("contact") or (enquiry.contact_id if enquiry else None),
            enquiry=enquiry,
            project_title=enquiry.description[:255] if enquiry else "",
            project_address=enquiry.project_address if enquiry else "",
        )
        if enquiry:
            enquiry.status = "proposal_created"
            enquiry.save(update_fields=["status"])

        messages.success(request, f"Fee Proposal {proposal.proposal_number} created - now fill in the details.")
        return redirect("proposal_builder", pk=proposal.pk)

    return render(request, "crm/proposal_create.html", {
        "active_nav": "proposals",
        "user_tenant": tenant,
        "enquiry": enquiry,
        "organisations": Organisation.objects.filter(tenant=tenant).order_by("legal_name"),
        "contacts": (enquiry.organisation.contacts.all() if enquiry else Contact.objects.filter(tenant=tenant)).order_by("first_name"),
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
def proposal_builder(request, pk):
    tenant = get_user_tenant(request)
    proposal = get_object_or_404(
        Proposal.objects.select_related("organisation", "contact", "signing_director", "selected_payment_term"),
        pk=pk, tenant=tenant,
    )
    if not can_edit_proposals(request.user):
        messages.error(request, "You don't have permission to edit Fee Proposals.")
        return redirect("proposal_detail", pk=proposal.pk)

    tab = request.GET.get("tab", "details")
    selected_modality_ids = set(proposal.modalities.values_list("id", flat=True))

    # ---------------- POST handling ----------------
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_details":
            before = {f: getattr(proposal, f) for f in [
                "project_title", "project_address", "contact_id", "is_individual_client",
                "enquiry_received_date", "project_budget", "budget_mode", "signing_director_id",
            ]}
            proposal.project_title = request.POST.get("project_title", "").strip()
            proposal.project_address = request.POST.get("project_address", "").strip()
            proposal.contact_id = request.POST.get("contact") or None
            proposal.is_individual_client = request.POST.get("is_individual_client") == "on"
            proposal.enquiry_received_date = request.POST.get("enquiry_received_date") or None
            proposal.project_budget = request.POST.get("project_budget") or None
            proposal.budget_mode = request.POST.get("budget_mode", proposal.budget_mode)
            proposal.signing_director_id = request.POST.get("signing_director") or None
            proposal.save()
            diff_and_log_update(request.user, tenant, proposal, before, "Updated via Fee Proposal Builder - Details tab")
            messages.success(request, "Details saved.")
            return redirect(f"/proposals/{proposal.pk}/builder/?tab=details")

        if action == "save_scope":
            new_modality_ids = set(int(x) for x in request.POST.getlist("modalities"))
            proposal.modalities.set(new_modality_ids)
            relevant_items = FPScopeItem.objects.filter(tenant=tenant).filter(
                Q(modality_id__in=new_modality_ids) | Q(modality__isnull=True)
            )
            checked_ids = set(int(x) for x in request.POST.getlist("scope_item"))
            to_include = [i for i in relevant_items if i.id in checked_ids]
            to_exclude = [i for i in relevant_items if i.id not in checked_ids]
            if to_include:
                proposal.deselected_scope_items.remove(*to_include)
            if to_exclude:
                proposal.deselected_scope_items.add(*to_exclude)
            log_audit(request.user, tenant, "update", proposal, reason="Updated via Fee Proposal Builder - Scope tab",
                      details=f"Modalities: {new_modality_ids}")
            messages.success(request, "Scope saved.")
            return redirect(f"/proposals/{proposal.pk}/builder/?tab=scope")

        if action == "save_exclusions":
            proposal.contract_administration_included = request.POST.get("contract_administration_included") == "on"
            proposal.novation_included = request.POST.get("novation_included") == "on"
            proposal.save(update_fields=["contract_administration_included", "novation_included"])

            relevant_items = FPExclusionItem.objects.filter(tenant=tenant).filter(
                Q(modality_id__in=selected_modality_ids) | Q(modality__isnull=True)
            )
            checked_ids = set(int(x) for x in request.POST.getlist("exclusion_item"))
            to_include = [i for i in relevant_items if i.id in checked_ids]
            to_exclude = [i for i in relevant_items if i.id not in checked_ids]
            if to_include:
                proposal.deselected_exclusion_items.remove(*to_include)
            if to_exclude:
                proposal.deselected_exclusion_items.add(*to_exclude)
            log_audit(request.user, tenant, "update", proposal, reason="Updated via Fee Proposal Builder - Exclusions tab")
            messages.success(request, "Exclusions saved.")
            return redirect(f"/proposals/{proposal.pk}/builder/?tab=exclusions")

        if action == "save_fees":
            proposal.ca_fee_type = request.POST.get("ca_fee_type", "")
            proposal.ca_fixed_fee = request.POST.get("ca_fixed_fee") or None
            proposal.save(update_fields=["ca_fee_type", "ca_fixed_fee"])

            ProposalFeeLine.objects.filter(proposal=proposal).delete()
            total = 0
            if proposal.budget_mode == "lump_sum":
                for stage_key, _ in ProposalFeeLine.STAGE_CHOICES:
                    amount = request.POST.get(f"amount_lump_{stage_key}") or 0
                    if float(amount or 0) > 0:
                        ProposalFeeLine.objects.create(tenant=tenant, proposal=proposal, stage=stage_key, modality=None, amount=amount)
                        total += float(amount)
            else:
                for modality_id in selected_modality_ids:
                    for stage_key, _ in ProposalFeeLine.STAGE_CHOICES:
                        amount = request.POST.get(f"amount_mod{modality_id}_{stage_key}") or 0
                        if float(amount or 0) > 0:
                            ProposalFeeLine.objects.create(tenant=tenant, proposal=proposal, stage=stage_key, modality_id=modality_id, amount=amount)
                            total += float(amount)
            if proposal.contract_administration_included and proposal.ca_fee_type == "fixed" and proposal.ca_fixed_fee:
                total += float(proposal.ca_fixed_fee)
            proposal.fee_amount = round(total, 2)
            proposal.save(update_fields=["fee_amount"])
            log_audit(request.user, tenant, "update", proposal, reason="Updated via Fee Proposal Builder - Fees tab",
                      details=f"New total: ${proposal.fee_amount}")
            messages.success(request, "Fees saved.")
            return redirect(f"/proposals/{proposal.pk}/builder/?tab=fees")

        if action == "save_terms":
            checked_clause_ids = set(int(x) for x in request.POST.getlist("term_clause"))
            mandatory_ids = set(FPTermClause.objects.filter(tenant=tenant, mandatory=True).values_list("id", flat=True))
            proposal.included_term_clauses.set(checked_clause_ids | mandatory_ids)
            proposal.selected_payment_term_id = request.POST.get("selected_payment_term") or None
            proposal.payment_term_override_text = request.POST.get("payment_term_override_text", "").strip()
            proposal.save(update_fields=["selected_payment_term", "payment_term_override_text"])
            log_audit(request.user, tenant, "update", proposal, reason="Updated via Fee Proposal Builder - Terms tab")
            messages.success(request, "Terms & Conditions saved.")
            return redirect(f"/proposals/{proposal.pk}/builder/?tab=terms")

    # ---------------- GET context per tab ----------------
    context = {
        "active_nav": "proposals",
        "user_tenant": tenant,
        "proposal": proposal,
        "tab": tab,
        "selected_modality_ids": selected_modality_ids,
        "all_modalities": Modality.objects.filter(tenant=tenant).order_by("name"),
        "all_contacts": proposal.organisation.contacts.all().order_by("first_name"),
        "all_users": User.objects.filter(profile__tenant=tenant, is_active=True).order_by("username"),
    }

    if tab == "scope":
        deselected_ids = set(proposal.deselected_scope_items.values_list("id", flat=True))
        general_items = FPScopeItem.objects.filter(tenant=tenant, modality__isnull=True).order_by("order")
        modality_items = {}
        for m in context["all_modalities"]:
            if m.id in selected_modality_ids:
                modality_items[m] = FPScopeItem.objects.filter(tenant=tenant, modality=m).order_by("order")
        context.update({
            "general_items": general_items,
            "modality_items": modality_items,
            "deselected_ids": deselected_ids,
        })

    if tab == "exclusions":
        deselected_ids = set(proposal.deselected_exclusion_items.values_list("id", flat=True))
        general_items = FPExclusionItem.objects.filter(
            tenant=tenant, modality__isnull=True, is_miscellaneous=False,
            is_contract_administration=False, is_novation=False,
        ).order_by("order")
        misc_items = FPExclusionItem.objects.filter(tenant=tenant, is_miscellaneous=True).order_by("order")
        ca_items = FPExclusionItem.objects.filter(tenant=tenant, is_contract_administration=True).order_by("order")
        novation_items = FPExclusionItem.objects.filter(tenant=tenant, is_novation=True).order_by("order")
        modality_items = {}
        for m in context["all_modalities"]:
            if m.id in selected_modality_ids:
                items = FPExclusionItem.objects.filter(tenant=tenant, modality=m).order_by("order")
                if items.exists():
                    modality_items[m] = items
        context.update({
            "general_items": general_items, "misc_items": misc_items,
            "ca_items": ca_items, "novation_items": novation_items,
            "modality_items": modality_items, "deselected_ids": deselected_ids,
        })

    if tab == 'fees':
        existing_lines_lump = {}
        existing_lines_per_modality = {}
        for fl in proposal.fee_lines.all():
            if fl.modality_id is None:
                existing_lines_lump[fl.stage] = fl.amount
            else:
                existing_lines_per_modality.setdefault(fl.modality_id, {})[fl.stage] = fl.amount
        context.update({
            "stage_choices": ProposalFeeLine.STAGE_CHOICES,
            "existing_lines_lump": existing_lines_lump,
            "existing_lines_per_modality": existing_lines_per_modality,
            "selected_modalities": [m for m in context["all_modalities"] if m.id in selected_modality_ids],
        })

    if tab == "terms":
        included_ids = set(proposal.included_term_clauses.values_list("id", flat=True))
        context.update({
            "all_clauses": FPTermClause.objects.filter(tenant=tenant).order_by("number"),
            "included_ids": included_ids,
            "all_payment_terms": FPPaymentTermOption.objects.filter(tenant=tenant).order_by("order"),
        })

    return render(request, "crm/proposal_builder.html", context)


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


@login_required
def contact_edit(request, pk):
    tenant = get_user_tenant(request)
    contact = get_object_or_404(Contact.objects.select_related("organisation"), pk=pk, tenant=tenant)

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "You must give a reason for this change.")
            return redirect("contact_edit", pk=contact.pk)

        before = {f: getattr(contact, f) for f in CONTACT_EDITABLE_FIELDS}

        contact.first_name = request.POST.get("first_name", contact.first_name).strip()
        contact.last_name = request.POST.get("last_name", contact.last_name).strip()
        contact.job_title = request.POST.get("job_title", "").strip()
        contact.email = request.POST.get("email", "").strip()
        contact.mobile = request.POST.get("mobile", "").strip()
        contact.office_phone = request.POST.get("office_phone", "").strip()
        contact.is_proposal_recipient = request.POST.get("is_proposal_recipient") == "on"
        contact.is_invoice_recipient = request.POST.get("is_invoice_recipient") == "on"
        contact.notes = request.POST.get("notes", "").strip()
        contact.save()

        changed = diff_and_log_update(request.user, tenant, contact, before, reason)
        if changed:
            messages.success(request, "Contact updated.")
        else:
            messages.success(request, "No changes were made.")
        return redirect("contact_detail", pk=contact.pk)

    return render(request, "crm/contact_edit.html", {
        "active_nav": "organisations",
        "user_tenant": tenant,
        "contact": contact,
    })
