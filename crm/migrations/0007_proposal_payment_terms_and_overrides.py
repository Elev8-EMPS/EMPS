import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0006_seed_fee_proposal_library"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="proposal",
            name="selected_payment_term",
        ),
        migrations.AlterField(
            model_name="proposal",
            name="payment_term_override_text",
            field=models.TextField(blank=True, help_text="Any additional payment terms note, on top of the selected options below."),
        ),
        migrations.CreateModel(
            name="ProposalPaymentTermSelection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("percentage", models.DecimalField(blank=True, decimal_places=2, help_text="Overrides the option's default percentage for this proposal - leave blank to use the default.", max_digits=5, null=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("option", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="crm.fppaymenttermoption")),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="payment_term_selections", to="crm.proposal")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"ordering": ["order"]},
        ),
        migrations.CreateModel(
            name="ProposalScopeItemOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("custom_text", models.TextField()),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scope_item_overrides", to="crm.proposal")),
                ("scope_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="crm.fpscopeitem")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"unique_together": {("proposal", "scope_item")}},
        ),
        migrations.CreateModel(
            name="ProposalExclusionItemOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("custom_text", models.TextField()),
                ("exclusion_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="crm.fpexclusionitem")),
                ("proposal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="exclusion_item_overrides", to="crm.proposal")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenants.tenant")),
            ],
            options={"unique_together": {("proposal", "exclusion_item")}},
        ),
    ]
