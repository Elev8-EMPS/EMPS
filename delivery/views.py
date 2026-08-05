from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.models import Team, Modality, ChecklistItemTemplate
from tenants.utils import get_user_tenant
from .models import Project, Milestone, Task, Document, TaskComment, ProjectChecklistItem, ProjectStakeholder


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
        projects = projects.filter(status=status)

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

    if request.method == "POST" and request.POST.get("action") == "add_modality":
        modality_id = request.POST.get("modality")
        if modality_id:
            project.modalities.add(modality_id)
            _generate_checklist_items(project, tenant, list(project.modalities.values_list("id", flat=True)))
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

    return render(request, "delivery/project_detail.html", {
        "active_nav": "projects",
        "user_tenant": tenant,
        "project": project,
        "tab": tab,
        "milestones": project.milestones.order_by("deadline") if tab == "milestones" else None,
        "tasks": project.tasks.order_by("due_date") if tab == "tasks" else None,
        "documents": project.documents.order_by("-uploaded_at") if tab == "documents" else None,
        "invoices": project.invoices.order_by("-due_date") if tab == "finance" else None,
        "open_todos": project.tasks.exclude(status__in=["completed", "cancelled"]).order_by("due_date")
        if tab == "overview" else None,
        "communications": project.communications.order_by("-occurred_at") if tab == "communications" else None,
        "checklist_items": checklist_items,
        "checklist_progress": checklist_progress,
        "checklist_summary": checklist_summary,
        "available_optional_items": available_optional_items,
        "stakeholders": stakeholders,
        "archived_stakeholders": archived_stakeholders,
        "available_contacts": available_contacts,
        "available_modalities": Modality.objects.filter(tenant=tenant).exclude(
            id__in=project.modalities.values_list("id", flat=True)
        ) if tab == "checklist" else None,
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
def milestone_list(request):
    tenant = get_user_tenant(request)
    milestones = Milestone.objects.filter(tenant=tenant) if tenant else Milestone.objects.none()

    status = request.GET.get("status", "").strip()
    if status:
        milestones = milestones.filter(status=status)

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
        "invoices": milestone.invoices.all(),
    })


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
    return render(request, "delivery/document_detail.html", {
        "active_nav": "documents",
        "user_tenant": tenant,
        "document": document,
    })
