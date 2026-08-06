from django.shortcuts import redirect

from .trusted_device import is_device_trusted

# Paths that must always work regardless of verification state, so
# nobody can ever get stuck in a redirect loop or lose access to
# managing their own 2FA.
EXEMPT_PREFIXES = (
    "/security/",
    "/admin/login/",
    "/admin/logout/",
    "/static/",
)


class RequireOTPForSuperusers(object):
    """
    Deliberately narrow scope: only superusers who have ALREADY
    confirmed a device are challenged for a code once per session.
    Everyone else (including staff without a device yet) is
    completely untouched - so this can never lock out an account
    that hasn't opted in and confirmed 2FA works for them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(EXEMPT_PREFIXES):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and user.is_superuser
            and not user.is_verified()
        ):
            from django_otp.plugins.otp_totp.models import TOTPDevice

            if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
                if is_device_trusted(request, user):
                    return self.get_response(request)
                return redirect(f"/security/verify-2fa/?next={request.path}")

        return self.get_response(request)
