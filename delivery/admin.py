from django.contrib import admin

from tenants.admin_mixins import ExportCsvMixin, TenantScopedAdmin
from .models import Project, Milestone, Task, Document


@admin.register(Project)
class ProjectAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("project_number", "name", "client_organisation", "project_manager", "status", "target_completion_date", "tenant")
    list_filter = ("status", "tenant")
    search_fields = ("project_number", "name", "client_organisation__legal_name")
    date_hierarchy = "start_date"


@admin.register(Milestone)
class MilestoneAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("project", "milestone_type", "deadline", "status", "responsible_user", "invoice_required", "tenant")
    list_filter = ("status", "milestone_type", "invoice_required", "director_approval_required", "tenant")
    search_fields = ("project__project_number", "project__name", "milestone_type")
    date_hierarchy = "deadline"


@admin.register(Task)
class TaskAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("title", "owner", "status", "priority", "due_date", "related_project", "tenant")
    list_filter = ("status", "priority", "category", "tenant")
    search_fields = ("title", "description")
    date_hierarchy = "due_date"


@admin.register(Document)
class DocumentAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("display_name", "related_project", "category", "document_type", "version", "uploaded_by", "uploaded_at", "tenant")
    list_filter = ("category", "document_type", "confidentiality", "tenant")
    search_fields = ("display_name", "original_filename")
    date_hierarchy = "uploaded_at"
