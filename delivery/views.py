from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
import datetime

from tenants.models import Team, Modality, ChecklistItemTemplate, DeadlineCategory
from tenants.utils import get_user_tenant, has_company_wide_scope, can_view_financials, can_edit_financials, can_view_document, visible_document_filter, require_delete_reason, diff_and_log_update, can_edit_proposals
from .models import Project, Milestone, Task, Document, TaskComment, ProjectChecklistItem, ProjectStakeholder, ProjectScopeAddition

PROJECT_EDITABLE_FIELDS = [
    "name", "address", "client_organisation_id", "billing_organisation_id", "primary_contact_id",
    "project_manager_id", "director_id", "status", "start_date", "target_completion_date", "completion_date",
    "original_proposal_id",
]


def _generate_checklist_items(project, tenant, modality_ids):
    """
    Creates ProjectChecklistItem rows from templates: every universal
    'always included' item (no modality), plus every 'always
    included' item for each selected modality. Skips duplicates if
    called again (e.g. a modality added after project creation).
    """
    templates = ChecklistItemTemplate.objects.filter(tenant=tenant, always_included=True).filter(
        Q(modality__isnull=True) | Q(modality_id__in=modality_ids)
    )
    existing_texts = set(project.checklist_items.values_list("text", flat=True))
    new_items = []
    for tmpl in templates:
        if tmpl.text in existing_texts:
            continue
        new_items.append(ProjectChecklistItem(
            tenant=tenant, project=project, modality=tmpl.modality, text=tmpl.text, order=tmpl.order,
        ))
    ProjectChecklistItem.objects.bulk_create(new_items)


@login_required
def stakeholder_edit(request, pk):
    tenant = get_user_tenant(request)
    stakeholder = get_object_or_404(ProjectStakeholder, pk=pk, tenant=tenant)
    project_pk = stakeholder.project_id

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "delete":
            reason = require_delete_reason(request)
            if not reason:
                messages.error(request, "You must give a reason to remove this person from the project.")
                return redirect(f"/projects/{project_pk}/?tab=people")
            from tenants.models import log_audit
            log_audit(request.user, tenant, "delete", stakeholder, reason=reason)
            stakeholder.delete()
            return redirect(f"/projects/{project_pk}/?tab=people")

        if action == "archive":
            stakeholder.is_archived = True
            stakeholder.save()
            return redirect(f"/projects/{project_pk}/?tab=people")

        if action == "unarchive":
            stakeholder.is_archived = False
            stakeholder.save()
            return redirect(f"/projects/{project_pk}/?tab=people")

        if action == "update":
            stakeholder.role = request.POST.get("role", stakeholder.role)
            contact_id = request.POST.get("contact")
            external_name = request.POST.get("external_name", "").strip()
            external_company = request.POST.get("external_company", "").strip()
            external_email = request.POST.get("external_email", "").strip()
            external_phone = request.POST.get("external_phone", "").strip()

            if contact_id:
                stakeholder.contact_id = contact_id
            elif external_name:
                stakeholder.contact = _find_or_create_contact_from_external(
                    tenant, external_name, external_company, external_email, external_phone
                )
            else:
                stakeholder.contact = None

            stakeholder.notes = request.POST.get("notes", "").strip()
            stakeholder.save()
            return redirect(f"/projects/{project_pk}/?tab=people")

    from crm.models import Contact
    available_contacts = Contact.objects.filter(tenant=tenant).order_by("first_name") if tenant else Contact.objects.none()

    return render(request, "delivery/stakeholder_edit.html", {
        "active_nav": "projects",
        "user_tenant": tenant,
        "stakeholder": stakeholder,
        "available_contacts": available_contacts,
    })


@login_required
def project_create(request):
    tenant = get_user_tenant(request)

    if request.method == "POST":
        project = Project(
            tenant=tenant,
            project_number=request.POST.get("project_number", "").strip(),
            name=request.POST.get("name", "").strip(),
            address=request.POST.get("address", "").strip(),
            start_date=request.POST.get("start_date") or None,
            target_completion_date=request.POST.get("target_completion_date") or None,
        )
        org_id = request.POST.get("client_organisation")
        if org_id:
            project.client_organisation_id = org_id
        pm_id = request.POST.get("project_manager")
        if pm_id:
            project.project_manager_id = pm_id

        modality_ids = [int(x) for x in request.POST.getlist("modalities")]

        if project.project_number and project.name and org_id:
            project.save()
            if modality_ids:
                project.modalities.set(modality_ids)
                for m_id in modality_ids:
                    ProjectScopeAddition.objects.get_or_create(
                        tenant=tenant, project=project, modality_id=m_id,
                        defaults={"is_original_scope": True, "added_by": request.user},
                    )
            _generate_checklist_items(project, tenant, modality_ids)
            return redirect("project_detail", pk=project.pk)

    from crm.models import Organisation
    organisations = Organisation.objects.filter(tenant=tenant).order_by("legal_name") if tenant else Organisation.objects.none()
    users = User.objects.filter(profile__tenant=tenant).order_by("username") if tenant else User.objects.none()
    modalities = Modality.objects.filter(tenant=tenant).order_by("name") if tenant else Modality.objects.none()

    return render(request, "delivery/project_create.html", {
        "active_nav": "projects",
        "user_tenant": tenant,
        "organisations": organisations,
        "users": users,
        "modalities": modalities,
    })


def _find_or_create_contact_from_external(tenant, name, company, email, phone):
    """
    When a stakeholder is added with just a name/company/email (no
    existing Contact picked), this creates a real Contact record -
    reusing an existing one by email if there's a match, so the same
    person added to multiple projects doesn't get duplicated. Also
    finds-or-creates the Organisation by company name, so the person
    shows up correctly grouped in the tenant-wide Contacts directory.
    """
    from crm.models import Contact, Organisation

    if not name:
        return None

    if email:
        existing = Contact.objects.filter(tenant=tenant, email__iexact=email).first()
        if existing:
            return existing

    organisation = None
    if company:
        organisation, _ = Organisation.objects.get_or_create(
            tenant=tenant, legal_name__iexact=company,
            defaults={"legal_name": company, "client_status": "prospect"},
        )

    parts = name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    return Contact.objects.create(
        tenant=tenant, organisation=organisation, first_name=first_name, last_name=last_name,
        email=email, mobile=phone,
    )


@login_required
def project_list(request):
    tenant = get_user_tenant(request)
    projects = Project.objects.filter(tenant=tenant) if tenant else Project.objects.none()

    q = request.GET.get("q", "").strip()
    if q:
        projects = projects.filter(name__icontains=q) | projects.filter(project_number__icontains=q)

    status = request.GET.get("status", "").strip()
    if status:
        projects = projects.filter(status__in=status.split(","))

    projects = projects.select_related("client_organisation").order_by("-start_date", "project_number")

    return render(request, "delivery/project_list.html", {
        "active_nav": "projects",
        "user_tenant": tenant,
        "projects": projects,
        "q": q,
        "status": status,
        "status_choices": Project.STATUS_CHOICES,
    })


@login_required
def project_detail(request, pk):
    tenant = get_user_tenant(request)
    project = get_object_or_404(
        Project.objects.select_related("client_organisation", "project_manager", "director"),
        pk=pk, tenant=tenant,
    )

    if request.method == "POST" and request.POST.get("action") == "update_core":
        can_edit_core = has_company_wide_scope(request.user) or request.user.id in (
            project.project_manager_id, project.director_id
        )
        if not can_edit_core:
            messages.error(request, "You don't have permission to edit this project's details.")
            return redirect(f"/projects/{project.pk}/")

        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "You must give a reason for this change.")
            return redirect(f"/projects/{project.pk}/?tab=edit")

        before = {f: getattr(project, f) for f in PROJECT_EDITABLE_FIELDS}

        project.name = request.POST.get("name", project.name).strip()
        project.address = request.POST.get("address", "").strip()
        project.client_organisation_id = request.POST.get("client_organisation") or project.client_organisation_id
        project.billing_organisation_id = request.POST.get("billing_organisation") or None
        project.primary_contact_id = request.POST.get("primary_contact") or None
        project.project_manager_id = request.POST.get("project_manager") or None
        project.director_id = request.POST.get("director") or None
        project.status = request.POST.get("status", project.status)
        project.start_date = request.POST.get("start_date") or None
        project.target_completion_date = request.POST.get("target_completion_date") or None
        project.completion_date = request.POST.get("completion_date") or None
        if can_edit_proposals(request.user):
            project.original_proposal_id = request.POST.get("original_proposal") or None
        project.save()

        changed = diff_and_log_update(request.user, tenant, project, before, reason)
        messages.success(request, "Project updated." if changed else "No changes were made.")
        return redirect(f"/projects/{project.pk}/")

    if request.method == "POST" and request.POST.get("action") == "add_modality":
        modality_id = request.POST.get("modality")
        if modality_id:
            project.modalities.add(modality_id)
            modality = Modality.objects.filter(id=modality_id, tenant=tenant).first()
            if modality:
                suffix = modality.code or modality.name[:1].upper()
                ProjectScopeAddition.objects.get_or_create(
                    tenant=tenant, project=project, modality=modality,
                    defaults={"is_original_scope": False, "suffix": suffix, "added_by": request.user},
                )
            _generate_checklist_items(project, tenant, list(project.modalities.values_list("id", flat=True)))
        return redirect(f"/projects/{project.pk}/?tab=checklist")

    if request.method == "POST" and request.POST.get("action") == "update_scope_budget":
        addition_id = request.POST.get("addition_id")
        addition = ProjectScopeAddition.objects.filter(id=addition_id, tenant=tenant, project=project).first()
        if addition:
            budget_raw = request.POST.get("budget_amount", "").strip()
            addition.budget_amount = budget_raw or None
            addition.save()
        return redirect(f"/projects/{project.pk}/?tab=checklist")

    if request.method == "POST" and request.POST.get("action") == "add_optional_item":
        template_id = request.POST.get("template_id")
        if template_id:
            tmpl = ChecklistItemTemplate.objects.filter(id=template_id, tenant=tenant).first()
            if tmpl and not project.checklist_items.filter(text=tmpl.text).exists():
                ProjectChecklistItem.objects.create(
                    tenant=tenant, project=project, modality=tmpl.modality, text=tmpl.text, order=tmpl.order,
                )
        return redirect(f"/projects/{project.pk}/?tab=checklist")

    if request.method == "POST" and request.POST.get("action") == "add_custom_item":
        text = request.POST.get("custom_text", "").strip()
        if text:
            ProjectChecklistItem.objects.create(tenant=tenant, project=project, text=text)
        return redirect(f"/projects/{project.pk}/?tab=checklist")

    if request.method == "POST" and request.POST.get("action") == "add_stakeholder":
        contact_id = request.POST.get("contact")
        external_name = request.POST.get("external_name", "").strip()
        external_company = request.POST.get("external_company", "").strip()
        external_email = request.POST.get("external_email", "").strip()
        external_phone = request.POST.get("external_phone", "").strip()

        stakeholder = ProjectStakeholder(
            tenant=tenant, project=project,
            role=request.POST.get("role", "other"),
            notes=request.POST.get("notes", "").strip(),
        )
        if contact_id:
            stakeholder.contact_id = contact_id
        elif external_name:
            # No existing contact picked - create (or reuse) a real
            # Contact record so this person shows up in the tenant-wide
            # Contacts directory, not just on this project.
            stakeholder.contact = _find_or_create_contact_from_external(
                tenant, external_name, external_company, external_email, external_phone
            )

        if stakeholder.contact_id:
            stakeholder.save()
        return redirect(f"/projects/{project.pk}/?tab=people")

    tab = request.GET.get("tab", "overview")

    checklist_items = None
    checklist_progress = None
    available_optional_items = None
    scope_additions = None
    if tab == "checklist":
        checklist_items = project.checklist_items.select_related("modality").order_by("modality__name", "order", "text")
        total = checklist_items.count()
        done = checklist_items.filter(is_done=True).count()
        checklist_progress = {"total": total, "done": done, "pct": round(done / total * 100) if total else 0}

        existing_texts = set(checklist_items.values_list("text", flat=True))
        modality_ids = list(project.modalities.values_list("id", flat=True))
        available_optional_items = ChecklistItemTemplate.objects.filter(
            tenant=tenant, always_included=False, modality_id__in=modality_ids
        ).exclude(text__in=existing_texts).select_related("modality")

        scope_additions = project.scope_additions.select_related("modality").order_by("-is_original_scope", "suffix")

    checklist_summary = None
    if tab == "overview":
        total = project.checklist_items.count()
        done = project.checklist_items.filter(is_done=True).count()
        checklist_summary = {"total": total, "done": done}

    stakeholders = None
    archived_stakeholders = None
    available_contacts = None
    if tab == "people":
        stakeholders = project.stakeholders.filter(is_archived=False).select_related("contact").order_by("role")
        archived_stakeholders = project.stakeholders.filter(is_archived=True).select_related("contact")
        from crm.models import Contact
        available_contacts = Contact.objects.filter(tenant=tenant).order_by("first_name") if tenant else Contact.objects.none()

    edit_organisations = edit_contacts = edit_users = edit_proposals = None
    can_edit_core = False
    can_link_proposal = False
    if tab == "edit":
        can_edit_core = has_company_wide_scope(request.user) or request.user.id in (
            project.project_manager_id, project.director_id
        )
        can_link_proposal = can_edit_proposals(request.user)
        from crm.models import Organisation, Contact, Proposal
        edit_organisations = Organisation.objects.filter(tenant=tenant).order_by("legal_name")
        edit_contacts = Contact.objects.filter(tenant=tenant).order_by("first_name")
        edit_users = User.objects.filter(profile__tenant=tenant, is_active=True).order_by("username")
        if can_link_proposal:
            edit_proposals = Proposal.objects.filter(tenant=tenant).select_related("organisation").order_by("-issue_date")

    return render(request, "delivery/project_detail.html", {
        "active_nav": "projects",
        "user_tenant": tenant,
        "project": project,
        "tab": tab,
        "milestones": project.milestones.order_by("deadline") if tab == "milestones" else None,
        "tasks": project.tasks.order_by("due_date") if tab == "tasks" else None,
        "documents": project.documents.filter(visible_document_filter(request.user)).order_by("-uploaded_at") if tab == "documents" else None,
        "invoices": project.invoices.order_by("-due_date") if tab == "finance" else None,
        "can_view_project_financials": can_view_financials(request.user) or request.user.id in (
            project.project_manager_id, project.director_id
        ),
        "payment_schedule": project.milestones.filter(invoice_required=True).order_by("deadline") if tab == "finance" else None,
        "responsible_teams": Team.objects.filter(
            tenant=tenant, modalities__in=project.modalities.all()
        ).distinct().prefetch_related("modalities", "members") if tab == "teams" else None,
        "open_todos": project.tasks.exclude(status__in=["completed", "cancelled"]).order_by("due_date")
        if tab == "overview" else None,
        "communications": project.communications.order_by("-occurred_at") if tab == "communications" else None,
        "checklist_items": checklist_items,
        "checklist_progress": checklist_progress,
        "checklist_summary": checklist_summary,
        "available_optional_items": available_optional_items,
        "scope_additions": scope_additions,
        "stakeholders": stakeholders,
        "archived_stakeholders": archived_stakeholders,
        "available_contacts": available_contacts,
        "available_modalities": Modality.objects.filter(tenant=tenant).exclude(
            id__in=project.modalities.values_list("id", flat=True)
        ) if tab == "checklist" else None,
        "edit_organisations": edit_organisations,
        "edit_contacts": edit_contacts,
        "edit_users": edit_users,
        "edit_proposals": edit_proposals,
        "can_edit_core": can_edit_core,
        "can_link_proposal": can_link_proposal,
    })


@login_required
def checklist_toggle(request, pk):
    tenant = get_user_tenant(request)
    item = get_object_or_404(ProjectChecklistItem, pk=pk, tenant=tenant)
    if request.method == "POST":
        item.is_done = not item.is_done
        item.done_by = request.user if item.is_done else None
        item.done_at = timezone.now() if item.is_done else None
        item.save()
    return redirect(f"/projects/{item.project_id}/?tab=checklist")


@login_required
def milestone_create(request):
    tenant = get_user_tenant(request)

    if request.method == "POST":
        milestone = Milestone(
            tenant=tenant,
            created_by=request.user,
            milestone_type=request.POST.get("milestone_type", "").strip(),
            deadline=request.POST.get("deadline") or None,
            deadline_time=request.POST.get("deadline_time") or None,
            notes=request.POST.get("notes", "").strip(),
            invoice_required=request.POST.get("invoice_required") == "on",
        )
        project_id = request.POST.get("project")
        category_id = request.POST.get("category")
        responsible_id = request.POST.get("responsible_user")
        payment_percentage = request.POST.get("payment_percentage", "").strip()

        if project_id:
            milestone.project_id = project_id
        if category_id:
            milestone.category_id = category_id
        if responsible_id:
            milestone.responsible_user_id = responsible_id
        if milestone.invoice_required and payment_percentage:
            try:
                milestone.payment_percentage = float(payment_percentage)
            except ValueError:
                pass

        if milestone.milestone_type and milestone.project_id and milestone.deadline:
            milestone.save()
            return redirect("milestone_detail", pk=milestone.pk)
        else:
            missing = []
            if not milestone.milestone_type:
                missing.append("a title")
            if not milestone.project_id:
                missing.append("a project")
            if not milestone.deadline:
                missing.append("a date")
            messages.error(request, f"Please fill in {' and '.join(missing)}.")

    preselected_project = request.POST.get("project") or request.GET.get("project", "")
    form_data = request.POST if request.method == "POST" else {}
    projects = Project.objects.filter(tenant=tenant).order_by("project_number") if tenant else Project.objects.none()
    users = User.objects.filter(profile__tenant=tenant).order_by("username") if tenant else User.objects.none()
    categories = DeadlineCategory.objects.filter(tenant=tenant).order_by("name") if tenant else DeadlineCategory.objects.none()

    return render(request, "delivery/milestone_create.html", {
        "active_nav": "milestones",
        "user_tenant": tenant,
        "projects": projects,
        "users": users,
        "categories": categories,
        "preselected_project": preselected_project,
        "form_data": form_data,
    })


@login_required
def milestone_edit(request, pk):
    tenant = get_user_tenant(request)
    milestone = get_object_or_404(Milestone.objects.select_related("project"), pk=pk, tenant=tenant)
    today = timezone.localtime(timezone.now()).date()
    is_past = milestone.deadline < today

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "set_status":
            # Allowed even for past deadlines - marking something done
            # (or reopening it) is exactly what you'd want to do once
            # its date has passed, unlike changing its title/date/etc.
            new_status = request.POST.get("status", "")
            valid_statuses = {v for v, _ in Milestone.STATUS_CHOICES}
            if new_status in valid_statuses:
                milestone.status = new_status
                milestone.save()
                messages.success(request, f"Marked as {milestone.get_status_display()}.")
            return redirect("milestone_detail", pk=milestone.pk)

        if is_past:
            messages.error(request, "This deadline is in the past and can't be edited or deleted - duplicate it to a new date instead.")
            return redirect("milestone_detail", pk=milestone.pk)

        if action == "delete":
            reason = require_delete_reason(request)
            if not reason:
                messages.error(request, "You must give a reason to delete this deadline.")
                return redirect("milestone_detail", pk=milestone.pk)
            from tenants.models import log_audit
            log_audit(request.user, tenant, "delete", milestone, reason=reason)
            project_pk = milestone.project_id
            milestone.delete()
            messages.success(request, "Deadline deleted.")
            return redirect("project_detail", pk=project_pk)

        milestone.milestone_type = request.POST.get("milestone_type", "").strip()
        milestone.deadline = request.POST.get("deadline") or milestone.deadline
        milestone.deadline_time = request.POST.get("deadline_time") or None
        milestone.notes = request.POST.get("notes", "").strip()
        milestone.invoice_required = request.POST.get("invoice_required") == "on"

        category_id = request.POST.get("category")
        milestone.category_id = category_id or None
        responsible_id = request.POST.get("responsible_user")
        milestone.responsible_user_id = responsible_id or None

        payment_percentage = request.POST.get("payment_percentage", "").strip()
        if milestone.invoice_required and payment_percentage:
            try:
                milestone.payment_percentage = float(payment_percentage)
            except ValueError:
                pass
        elif not milestone.invoice_required:
            milestone.payment_percentage = None

        if milestone.milestone_type and milestone.deadline:
            milestone.save()
            messages.success(request, "Deadline updated.")
            return redirect("milestone_detail", pk=milestone.pk)

    categories = DeadlineCategory.objects.filter(tenant=tenant).order_by("name") if tenant else DeadlineCategory.objects.none()
    users = User.objects.filter(profile__tenant=tenant).order_by("username") if tenant else User.objects.none()

    return render(request, "delivery/milestone_edit.html", {
        "active_nav": "milestones",
        "user_tenant": tenant,
        "milestone": milestone,
        "is_past": is_past,
        "categories": categories,
        "users": users,
    })


@login_required
def milestone_duplicate(request, pk):
    tenant = get_user_tenant(request)
    original = get_object_or_404(Milestone.objects.select_related("project"), pk=pk, tenant=tenant)

    if request.method == "POST":
        new_deadline = request.POST.get("deadline")
        if new_deadline:
            copy = Milestone.objects.create(
                tenant=tenant, project=original.project, created_by=request.user,
                milestone_type=request.POST.get("milestone_type", original.milestone_type).strip() or original.milestone_type,
                category=original.category, deadline=new_deadline,
                deadline_time=request.POST.get("deadline_time") or None,
                responsible_user=original.responsible_user,
                invoice_required=original.invoice_required,
                payment_percentage=original.payment_percentage,
                notes=original.notes,
            )
            messages.success(request, "Deadline duplicated to the new date.")
            return redirect("milestone_detail", pk=copy.pk)

    return render(request, "delivery/milestone_duplicate.html", {
        "active_nav": "milestones",
        "user_tenant": tenant,
        "original": original,
    })


@login_required
def milestone_list(request):
    tenant = get_user_tenant(request)
    today = timezone.localtime(timezone.now()).date()
    milestones = Milestone.objects.filter(tenant=tenant) if tenant else Milestone.objects.none()

    status = request.GET.get("status", "").strip()
    if status:
        milestones = milestones.filter(status__in=status.split(","))

    due = request.GET.get("due", "").strip()
    if due == "today":
        milestones = milestones.filter(deadline=today).exclude(status__in=["issued", "closed", "paid"])
    elif due == "overdue":
        milestones = milestones.filter(deadline__lt=today).exclude(status__in=["issued", "closed", "paid"])

    q = request.GET.get("q", "").strip()
    if q:
        milestones = milestones.filter(milestone_type__icontains=q) | milestones.filter(
            project__project_number__icontains=q
        )

    milestones = milestones.select_related("project", "responsible_user").order_by("deadline")

    return render(request, "delivery/milestone_list.html", {
        "active_nav": "milestones",
        "user_tenant": tenant,
        "milestones": milestones,
        "q": q,
        "status": status,
        "status_choices": Milestone.STATUS_CHOICES,
    })


@login_required
def milestone_detail(request, pk):
    tenant = get_user_tenant(request)
    milestone = get_object_or_404(
        Milestone.objects.select_related("project", "responsible_user"), pk=pk, tenant=tenant
    )
    return render(request, "delivery/milestone_detail.html", {
        "active_nav": "milestones",
        "user_tenant": tenant,
        "milestone": milestone,
        "is_past": milestone.deadline < timezone.localtime(timezone.now()).date(),
        "invoices": milestone.invoices.all(),
        "can_view_project_financials": can_view_financials(request.user) or request.user.id in (
            milestone.project.project_manager_id, milestone.project.director_id
        ),
    })


@login_required
def due_reminders(request):
    """
    Polled by every logged-in page every ~60s (see base.html) to
    surface an in-app popup for deadlines whose scheduled time has
    just arrived. A deadline is relevant to someone if they're the
    responsible person, this project's manager/director, a
    Director/Company Admin, or on a team whose discipline matches
    the project's modalities - same matching used on the Calendar.
    """
    tenant = get_user_tenant(request)
    if tenant is None:
        return JsonResponse({"reminders": []})

    now = timezone.localtime(timezone.now())
    today = now.date()
    window_start = (now - datetime.timedelta(minutes=20)).time()

    candidates = Milestone.objects.filter(
        tenant=tenant, deadline=today, deadline_time__isnull=False,
        deadline_time__lte=now.time(), deadline_time__gte=window_start,
    ).select_related("project")

    if not has_company_wide_scope(request.user):
        my_team_modality_ids = list(
            request.user.teams.filter(tenant=tenant).values_list("modalities__id", flat=True).distinct()
        )
        modality_q = Q(project__modalities__id__in=my_team_modality_ids) if my_team_modality_ids else Q()
        candidates = candidates.filter(
            Q(responsible_user=request.user)
            | Q(project__project_manager=request.user)
            | Q(project__director=request.user)
            | modality_q
        ).distinct()

    return JsonResponse({"reminders": [
        {
            "id": m.pk,
            "title": m.milestone_type,
            "project_number": m.project.project_number,
            "time": m.deadline_time.strftime("%H:%M"),
            "category": m.category.name if m.category_id else "",
            "url": f"/milestones/{m.pk}/",
        }
        for m in candidates
    ]})


@login_required
def task_list(request):
    tenant = get_user_tenant(request)
    tasks = Task.objects.filter(tenant=tenant) if tenant else Task.objects.none()

    status = request.GET.get("status", "").strip()
    if status:
        tasks = tasks.filter(status=status)

    priority = request.GET.get("priority", "").strip()
    if priority:
        tasks = tasks.filter(priority=priority)

    scope = request.GET.get("scope", "mine").strip()
    if scope == "mine":
        tasks = tasks.filter(
            Q(owner=request.user) | Q(assigned_team__members=request.user)
        ).distinct()
    # scope == "all" -> no extra filter, tenant staff can see everything

    owner_id = request.GET.get("owner", "").strip()
    if owner_id:
        tasks = tasks.filter(owner_id=owner_id)

    team_id = request.GET.get("team", "").strip()
    if team_id:
        tasks = tasks.filter(assigned_team_id=team_id)

    q = request.GET.get("q", "").strip()
    if q:
        tasks = tasks.filter(title__icontains=q)

    tasks = tasks.select_related("owner", "assigned_team", "related_project", "created_by").order_by("due_date")

    return render(request, "delivery/task_list.html", {
        "active_nav": "tasks",
        "user_tenant": tenant,
        "tasks": tasks,
        "q": q,
        "status": status,
        "priority": priority,
        "scope": scope,
        "owner_id": owner_id,
        "team_id": team_id,
        "status_choices": Task.STATUS_CHOICES,
        "priority_choices": Task.PRIORITY_CHOICES,
        "users": User.objects.filter(profile__tenant=tenant).order_by("username") if tenant else User.objects.none(),
        "teams": Team.objects.filter(tenant=tenant).order_by("name") if tenant else Team.objects.none(),
    })


@login_required
def task_create(request):
    tenant = get_user_tenant(request)

    if request.method == "POST":
        task = Task(
            tenant=tenant,
            created_by=request.user,
            title=request.POST.get("title", "").strip(),
            description=request.POST.get("description", "").strip(),
            category=request.POST.get("category", ""),
            priority=request.POST.get("priority", "normal"),
            due_date=request.POST.get("due_date") or None,
        )
        project_id = request.POST.get("related_project")
        if project_id:
            task.related_project_id = project_id

        assign_to = request.POST.get("assign_to")  # "user:<id>" or "team:<id>"
        if assign_to and assign_to.startswith("user:"):
            task.owner_id = int(assign_to.split(":")[1])
        elif assign_to and assign_to.startswith("team:"):
            task.assigned_team_id = int(assign_to.split(":")[1])

        if task.title:
            task.save()
            return redirect("task_detail", pk=task.pk)

    projects = Project.objects.filter(tenant=tenant).order_by("project_number") if tenant else Project.objects.none()
    users = User.objects.filter(profile__tenant=tenant).order_by("username") if tenant else User.objects.none()
    teams = Team.objects.filter(tenant=tenant).order_by("name") if tenant else Team.objects.none()

    return render(request, "delivery/task_create.html", {
        "active_nav": "tasks",
        "user_tenant": tenant,
        "projects": projects,
        "users": users,
        "teams": teams,
        "category_choices": Task.CATEGORY_CHOICES,
        "priority_choices": Task.PRIORITY_CHOICES,
    })


@login_required
def task_detail(request, pk):
    tenant = get_user_tenant(request)
    task = get_object_or_404(
        Task.objects.select_related("owner", "related_project", "related_milestone", "created_by", "assigned_team"),
        pk=pk, tenant=tenant,
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "comment":
            body = request.POST.get("body", "").strip()
            if body:
                TaskComment.objects.create(tenant=tenant, task=task, author=request.user, body=body)
        elif action == "complete":
            task.status = "completed"
            task.completed_at = timezone.now()
            task.save()
        elif action == "reopen":
            task.status = "in_progress"
            task.completed_at = None
            task.save()
        return redirect("task_detail", pk=task.pk)

    return render(request, "delivery/task_detail.html", {
        "active_nav": "tasks",
        "user_tenant": tenant,
        "task": task,
        "comments": task.comments.select_related("author"),
    })


@login_required
def document_list(request):
    tenant = get_user_tenant(request)
    documents = Document.objects.filter(tenant=tenant) if tenant else Document.objects.none()
    documents = documents.filter(visible_document_filter(request.user))

    category = request.GET.get("category", "").strip()
    if category:
        documents = documents.filter(category=category)

    q = request.GET.get("q", "").strip()
    if q:
        documents = documents.filter(display_name__icontains=q) | documents.filter(
            original_filename__icontains=q
        )

    documents = documents.select_related("related_project", "uploaded_by").order_by("-uploaded_at")

    return render(request, "delivery/document_list.html", {
        "active_nav": "documents",
        "user_tenant": tenant,
        "documents": documents,
        "q": q,
        "category": category,
    })


@login_required
def document_detail(request, pk):
    tenant = get_user_tenant(request)
    document = get_object_or_404(
        Document.objects.select_related("related_project", "uploaded_by"), pk=pk, tenant=tenant
    )
    if not can_view_document(request.user, document):
        messages.error(request, "You don't have permission to view this document.")
        return redirect("document_list")
    return render(request, "delivery/document_detail.html", {
        "active_nav": "documents",
        "user_tenant": tenant,
        "document": document,
    })
