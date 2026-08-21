from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0008_proposaltermclauseoverride"),
    ]

    operations = [
        migrations.AlterField(
            model_name="proposalfeeline",
            name="stage",
            field=models.CharField(
                help_text="One of the 3 standard stage keys above, OR free text for a custom stage added on this proposal only.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="proposalfeeline",
            name="stage_label",
            field=models.CharField(
                blank=True,
                help_text="Display name for a custom stage - blank for the 3 standard stages, which use their fixed labels above.",
                max_length=100,
            ),
        ),
    ]
