from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from tenants.utils import get_user_tenant
from .models import Project, Milestone, Task, Document


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

    q = request.GET.get("q", "").strip()
    if q:
        tasks = tasks.filter(title__icontains=q)

    tasks = tasks.select_related("owner", "related_project").order_by("due_date")

    return render(request, "delivery/task_list.html", {
        "active_nav": "tasks",
        "user_tenant": tenant,
        "tasks": tasks,
        "q": q,
        "status": status,
        "priority": priority,
        "status_choices": Task.STATUS_CHOICES,
        "priority_choices": Task.PRIORITY_CHOICES,
    })


@login_required
def task_detail(request, pk):
    tenant = get_user_tenant(request)
    task = get_object_or_404(
        Task.objects.select_related("owner", "related_project", "related_milestone"), pk=pk, tenant=tenant
    )
    return render(request, "delivery/task_detail.html", {
        "active_nav": "tasks",
        "user_tenant": tenant,
        "task": task,
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
