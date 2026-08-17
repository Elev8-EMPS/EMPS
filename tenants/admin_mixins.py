import csv

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render


class AuditedAdminMixin:
    """
    Mixin for any ModelAdmin that should feed the shared Audit Log:
    - Every create/update via Admin is logged automatically.
    - Every delete (single record, or a bulk 'Delete selected' action)
      is BLOCKED until a reason is typed in - no reason, no delete.
    Put this first in the class bases, ahead of TenantScopedAdmin, e.g.
    class FooAdmin(AuditedAdminMixin, TenantScopedAdmin, admin.ModelAdmin).
    """

    def save_model(self, request, obj, form, change):
        from .models import log_audit
        super().save_model(request, obj, form, change)
        tenant = getattr(obj, "tenant", None)
        log_audit(request.user, tenant, "update" if change else "create", obj)

    def delete_view(self, request, object_id, extra_context=None):
        obj = self.get_object(request, object_id)
        if request.method == "POST":
            reason = request.POST.get("audit_reason", "").strip()
            if not reason:
                messages.error(request, "You must give a reason before this can be deleted.")
                return self._render_delete_reason_prompt(request, obj)
            from .models import log_audit
            tenant = getattr(obj, "tenant", None)
            log_audit(request.user, tenant, "delete", obj, reason=reason)
        return super().delete_view(request, object_id, extra_context)

    def _render_delete_reason_prompt(self, request, obj):
        return render(request, "admin/delete_reason_prompt.html", {
            "object": obj,
            "object_id": obj.pk,
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
        })

    def delete_queryset(self, request, queryset):
        # Bulk 'Delete selected' action - Admin doesn't give us a way
        # to collect a reason mid-action, so route people to delete
        # records one at a time instead, where the reason prompt applies.
        messages.error(
            request,
            "Bulk delete is disabled here - a reason is required for every deletion, "
            "so please delete records one at a time from each record's own Delete button.",
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


class TenantScopedAdmin:
    """
    Mixin for any ModelAdmin whose model has a `tenant` field.

    - Superusers: see the tenant field and every tenant's records
      (needed while there's only one company, and useful later for
      cross-tenant support/admin work).
    - Regular users with a tenant on their profile: the tenant field
      disappears from the add/edit form entirely, gets auto-filled
      on save, and the list view only ever shows their own tenant's
      records - so day to day, nobody ever has to think about tenant
      at all.
    - Regular users with NO tenant on their profile yet: see nothing,
      rather than accidentally seeing everything. Assign them a
      tenant in Admin -> Users -> (their profile) to fix this.
    """

    def _user_tenant(self, request):
        if request.user.is_superuser:
            return None  # signals "no restriction" for superusers
        profile = getattr(request.user, "profile", None)
        return profile.tenant if profile else None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        tenant = self._user_tenant(request)
        return qs.filter(tenant=tenant) if tenant else qs.none()

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if not request.user.is_superuser:
            exclude.append("tenant")
        return exclude

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.tenant = self._user_tenant(request)
        super().save_model(request, obj, form, change)


class ExportCsvMixin:
    """
    Adds an 'Export selected as CSV' action to any ModelAdmin that
    inherits this. Exports exactly the columns shown in list_display.
    """

    def export_as_csv(self, request, queryset):
        field_names = [f for f in self.list_display if f != "outstanding_amount_display"]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f"attachment; filename={self.model._meta.verbose_name_plural}.csv"
        writer = csv.writer(response)
        writer.writerow(field_names)
        for obj in queryset:
            row = []
            for field in field_names:
                value = getattr(obj, field, "")
                if callable(value):
                    value = value()
                row.append(str(value) if value is not None else "")
            writer.writerow(row)
        return response

    export_as_csv.short_description = "Export selected as CSV"
    actions = ["export_as_csv"]
