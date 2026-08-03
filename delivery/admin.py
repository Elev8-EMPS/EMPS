from django.contrib import admin

from tenants.admin_mixins import ExportCsvMixin, TenantScopedAdmin
from .models import Project, Milestone, Task, Document, TaskComment, ProjectChecklistItem


@admin.register(Project)
class ProjectAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("project_number", "name", "client_organisation", "project_manager", "status", "target_completion_date", "tenant")
    list_filter = ("status", "tenant")
    search_fields = ("project_number", "name", "client_organisation__legal_name")
    date_hierarchy = "start_date"
    filter_horizontal = ("modalities",)


@admin.register(Milestone)
class MilestoneAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("project", "milestone_type", "deadline", "status", "responsible_user", "invoice_required", "tenant")
    list_filter = ("status", "milestone_type", "invoice_required", "director_approval_required", "tenant")
    search_fields = ("project__project_number", "project__name", "milestone_type")
    date_hierarchy = "deadline"


@admin.register(Task)
class TaskAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("title", "owner", "assigned_team", "status", "priority", "category", "due_date", "created_by", "tenant")
    list_filter = ("status", "priority", "category", "assigned_team", "tenant")
    search_fields = ("title", "description")
    date_hierarchy = "due_date"

    def save_model(self, request, obj, form, change):
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Document)
class DocumentAdmin(TenantScopedAdmin, ExportCsvMixin, admin.ModelAdmin):
    list_display = ("display_name", "related_project", "category", "document_type", "version", "uploaded_by", "uploaded_at", "tenant")
    list_filter = ("category", "document_type", "confidentiality", "tenant")
    search_fields = ("display_name", "original_filename")
    date_hierarchy = "uploaded_at"


@admin.register(TaskComment)
class TaskCommentAdmin(TenantScopedAdmin, admin.ModelAdmin):
    list_display = ("task", "author", "created_at", "tenant")
    list_filter = ("tenant",)


@admin.register(ProjectChecklistItem)
class ProjectChecklistItemAdmin(TenantScopedAdmin, admin.ModelAdmin):
    list_display = ("text", "project", "modality", "is_done", "tenant")
    list_filter = ("is_done", "modality", "tenant")
