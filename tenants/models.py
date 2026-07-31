import uuid

from django.db import models


class Tenant(models.Model):
    """
    One row per company using EPMS.
    Only one row exists today - the platform is built to support
    more without a rewrite when that becomes real.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TenantModel(models.Model):
    """
    Abstract base class - every business record inherits from this.
    Every query against a tenant-owned table MUST filter by tenant.
    This is what keeps one company's data from ever leaking into another's.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
