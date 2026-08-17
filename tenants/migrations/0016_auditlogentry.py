import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenants", "0015_permission_domain_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLogEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("create", "Create"), ("update", "Update"), ("delete", "Delete")], max_length=10)),
                ("model_name", models.CharField(help_text="e.g. 'delivery.Project'", max_length=100)),
                ("object_id", models.CharField(max_length=50)),
                ("object_repr", models.CharField(help_text="What the record looked like at the time, so the log stays readable even after a delete.", max_length=255)),
                ("reason", models.TextField(blank=True)),
                ("details", models.TextField(blank=True, help_text="Optional extra context, e.g. which fields changed.")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_entries", to="tenants.tenant")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audit_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name_plural": "Audit log entries",
                "ordering": ["-created_at"],
            },
        ),
    ]
