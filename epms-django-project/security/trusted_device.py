"""
'Trust this device' for 2FA: after a successful code entry, a signed
cookie lets that same browser skip the challenge until it expires.
Signed (not encrypted) - can't be forged without the server's
SECRET_KEY, but isn't meant to be secret itself, same approach
Django uses for its own session/CSRF cookies.
"""

from django.conf import settings
from django.core import signing

COOKIE_NAME = "epms_trusted_device"
SALT = "epms.trusted_device.v1"


def _signer():
    return signing.TimestampSigner(salt=SALT)


def set_trusted_device_cookie(response, user):
    value = _signer().sign(str(user.pk))
    max_age = settings.TRUSTED_DEVICE_HOURS * 3600
    response.set_cookie(
        COOKIE_NAME, value, max_age=max_age, httponly=True, samesite="Lax",
        secure=not settings.DEBUG,
    )


def is_device_trusted(request, user):
    raw = request.COOKIES.get(COOKIE_NAME)
    if not raw:
        return False
    try:
        unsigned = _signer().unsign(raw, max_age=settings.TRUSTED_DEVICE_HOURS * 3600)
    except signing.BadSignature:
        return False
    return unsigned == str(user.pk)
