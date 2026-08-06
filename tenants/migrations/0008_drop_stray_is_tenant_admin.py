from django.db import migrations


def drop_stray_column(apps, schema_editor):
    """
    Production's tenants_userprofile table has an 'is_tenant_admin'
    column that isn't part of any current model or migration history -
    it must have been added outside Django's normal migration
    tracking at some point. It's NOT NULL with no default, so every
    new UserProfile insert fails. Since nothing in the current code
    uses this field, the correct fix is to remove it.

    Only runs on PostgreSQL (production) - local SQLite dev databases
    never had this column, so this is a safe no-op there.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("ALTER TABLE tenants_userprofile DROP COLUMN IF EXISTS is_tenant_admin")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0007_modality_code"),
    ]

    operations = [
        migrations.RunPython(drop_stray_column, noop_reverse),
    ]
