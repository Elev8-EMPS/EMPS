from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.models import Team
from tenants.utils import get_user_tenant
from .models import Project, Milestone, Task, Document, TaskComment


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

    tab = request.GET.get("tab", "overview")

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
    })


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
