from django.db import migrations, models


ACCESS_LEVEL_CHOICES = [
    ("", "Use role default"),
    ("none", "None"),
    ("view", "View only"),
    ("edit", "View & edit"),
]
BINARY_ACCESS_CHOICES = [
    ("", "Use role default"),
    ("none", "None"),
    ("edit", "Full access"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0014_deadlinecategory_color"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="userprofile",
            name="can_manage_proposals",
        ),
        migrations.AddField(
            model_name="userprofile",
            name="fees_access",
            field=models.CharField(blank=True, choices=ACCESS_LEVEL_CHOICES, max_length=10),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="financials_access",
            field=models.CharField(blank=True, choices=ACCESS_LEVEL_CHOICES, max_length=10),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="confidential_access",
            field=models.CharField(blank=True, choices=BINARY_ACCESS_CHOICES, max_length=10),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="company_admin_access",
            field=models.CharField(blank=True, choices=BINARY_ACCESS_CHOICES, max_length=10),
        ),
    ]
