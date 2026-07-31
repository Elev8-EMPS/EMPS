import csv

from django.http import HttpResponse


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
