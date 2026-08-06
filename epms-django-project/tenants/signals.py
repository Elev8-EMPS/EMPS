from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=User)
def ensure_profile_exists(sender, instance, created, **kwargs):
    """Every user gets a profile automatically, so there's always
    somewhere to assign their tenant - even before an admin sets it."""
    UserProfile.objects.get_or_create(user=instance)
