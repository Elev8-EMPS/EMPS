import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0007_proposal_payment_terms_and_overrides"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProposalTermClauseOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("custom_text", models.TextField()),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="term_clause_overrides", to="crm.proposal")),
                ("term_clause", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="crm.fptermclause")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"unique_together": {("proposal", "term_clause")}},
        ),
    ]
