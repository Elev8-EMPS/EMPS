import csv

from django.http import HttpResponse


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
