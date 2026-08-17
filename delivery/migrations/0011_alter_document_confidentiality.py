from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delivery", "0010_milestone_category_milestone_created_by_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="confidentiality",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Standard - visible to anyone with project access"),
                    ("fee_proposal", "Fee Proposal - Directors/Admin/Proposal access only"),
                    ("confidential", "Confidential - Directors/Admin only"),
                ],
                max_length=20,
            ),
        ),
    ]
