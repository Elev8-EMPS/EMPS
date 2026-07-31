from django.contrib import admin

from .models import Project, Milestone, Task, Document


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("project_number", "name", "client_organisation", "status", "tenant")
    list_filter = ("status", "tenant")
    search_fields = ("project_number", "name")


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("project", "milestone_type", "deadline", "status", "tenant")
    list_filter = ("status", "tenant")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "priority", "due_date", "tenant")
    list_filter = ("status", "priority", "tenant")


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("display_name", "related_project", "category", "version", "tenant")
    list_filter = ("category", "tenant")
