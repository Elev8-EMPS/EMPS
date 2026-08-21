from django.db import migrations


def delete_none_overrides(apps, schema_editor):
    """Cleans up the fallout from a bug where an empty wording-override
    box rendered as the literal word 'None' instead of blank, which
    then got saved as if it were real custom text on every untouched
    item. This deletes any override row where the saved text is
    exactly 'None' - a real user would never intentionally type just
    that word as a full replacement for a scope/exclusion/clause."""
    for model_name in ["ProposalScopeItemOverride", "ProposalExclusionItemOverride", "ProposalTermClauseOverride"]:
        Model = apps.get_model("crm", model_name)
        Model.objects.filter(custom_text="None").delete()


def noop_reverse(apps, schema_editor):
    pass  # Nothing sensible to restore - the deleted rows were corrupted data, not real edits.


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0009_proposalfeeline_custom_stages"),
    ]

    operations = [
        migrations.RunPython(delete_none_overrides, noop_reverse),
    ]
