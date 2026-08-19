import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0004_alter_contact_organisation"),
        ("tenants", "0016_auditlogentry"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FPTermClause",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("number", models.PositiveIntegerField()),
                ("text", models.TextField()),
                ("mandatory", models.BooleanField(default=False)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"ordering": ["number"]},
        ),
        migrations.CreateModel(
            name="FPPaymentTermOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("text", models.TextField()),
                ("default_percentage", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"ordering": ["order"]},
        ),
        migrations.CreateModel(
            name="FPScopeItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("text", models.TextField()),
                ("order", models.PositiveIntegerField(default=0)),
                ("modality", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="fp_scope_items", to="tenants.modality")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"ordering": ["modality_id", "order"]},
        ),
        migrations.CreateModel(
            name="FPExclusionItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_miscellaneous", models.BooleanField(default=False)),
                ("is_contract_administration", models.BooleanField(default=False)),
                ("is_novation", models.BooleanField(default=False)),
                ("text", models.TextField()),
                ("order", models.PositiveIntegerField(default=0)),
                ("modality", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="fp_exclusion_items", to="tenants.modality")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"ordering": ["modality_id", "order"]},
        ),
        migrations.AddField(
            model_name="proposal",
            name="project_title",
            field=models.CharField(blank=True, help_text="e.g. 'Proposed mixed use development' - shown on the cover page.", max_length=255),
        ),
        migrations.AddField(
            model_name="proposal",
            name="project_address",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="proposal",
            name="enquiry_received_date",
            field=models.DateField(blank=True, help_text="Feeds the T&C clause referencing when the enquiry/info was received.", null=True),
        ),
        migrations.AddField(
            model_name="proposal",
            name="is_individual_client",
            field=models.BooleanField(default=False, help_text="If ticked, the 'Client:' line is dropped from the cover page - use for a person, not a company."),
        ),
        migrations.AddField(
            model_name="proposal",
            name="project_budget",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="The project construction budget referenced in the standard T&Cs (distinct from the fee amount).", max_digits=14, null=True),
        ),
        migrations.AddField(
            model_name="proposal",
            name="budget_mode",
            field=models.CharField(choices=[("lump_sum", "One combined budget"), ("per_modality", "Split by modality")], default="lump_sum", max_length=20),
        ),
        migrations.AddField(
            model_name="proposal",
            name="modalities",
            field=models.ManyToManyField(blank=True, help_text="Which disciplines this proposal covers - drives which Our Scope / Exclusions sections are included.", related_name="proposals", to="tenants.modality"),
        ),
        migrations.AddField(
            model_name="proposal",
            name="deselected_scope_items",
            field=models.ManyToManyField(blank=True, help_text="Items that WOULD be included by the selected modalities, but have been individually unticked.", related_name="deselected_on_proposals", to="crm.fpscopeitem"),
        ),
        migrations.AddField(
            model_name="proposal",
            name="deselected_exclusion_items",
            field=models.ManyToManyField(blank=True, related_name="deselected_on_proposals", to="crm.fpexclusionitem"),
        ),
        migrations.AddField(
            model_name="proposal",
            name="included_term_clauses",
            field=models.ManyToManyField(blank=True, help_text="Which of the standard T&C clauses appear on this proposal.", related_name="included_on_proposals", to="crm.fptermclause"),
        ),
        migrations.AddField(
            model_name="proposal",
            name="selected_payment_term",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="proposals", to="crm.fppaymenttermoption"),
        ),
        migrations.AddField(
            model_name="proposal",
            name="payment_term_override_text",
            field=models.TextField(blank=True, help_text="If set, overrides the selected payment term's default wording/percentages for this proposal."),
        ),
        migrations.AddField(
            model_name="proposal",
            name="contract_administration_included",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="proposal",
            name="ca_fee_type",
            field=models.CharField(blank=True, choices=[("fixed", "Fixed Fee"), ("hourly", "Hourly Rates")], max_length=10),
        ),
        migrations.AddField(
            model_name="proposal",
            name="ca_fixed_fee",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="proposal",
            name="novation_included",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="proposal",
            name="signing_director",
            field=models.ForeignKey(blank=True, help_text="Whose name/signature block appears at the end of the T&Cs.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="signed_proposals", to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name="ProposalFeeLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("stage", models.CharField(choices=[("site_inspection", "Site Inspection & Report"), ("design_development", "Design Development"), ("contract_design_documentation", "Contract Design & Documentation")], max_length=40)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("included", models.BooleanField(default=True, help_text="Whether this stage appears on the proposal at all.")),
                ("modality", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="tenants.modality")),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fee_lines", to="crm.proposal")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"ordering": ["stage", "modality_id"]},
        ),
    ]
