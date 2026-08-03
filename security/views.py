import base64
import io

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice


@login_required
def setup_2fa(request):
    """
    Self-service two-factor setup. Deliberately does NOT lock anyone
    out - this only lets a user add and confirm a device. Actual
    enforcement (requiring a verified device to use the app) is a
    separate, later step, done only once real users have confirmed
    their device works. This staged approach matters because the
    free Render tier has no Shell access - a lockout here would be
    very hard to recover from.
    """
    existing = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()

    if request.method == "POST":
        token = request.POST.get("token", "").strip()
        device_id = request.POST.get("device_id")
        try:
            device = TOTPDevice.objects.get(id=device_id, user=request.user, confirmed=False)
        except TOTPDevice.DoesNotExist:
            messages.error(request, "Setup session expired - scan the QR code again below.")
            return redirect("setup_2fa")

        if device.verify_token(token):
            device.confirmed = True
            device.save()
            otp_login(request, device)
            messages.success(request, "Two-factor authentication is now set up and confirmed for your account.")
            return redirect("setup_2fa")
        else:
            messages.error(request, "That code didn't match - check the time on your phone and try again.")
            device.delete()  # start fresh rather than leaving a stale unconfirmed device

    # GET: show existing confirmed device, or create a new pending one to scan
    pending_device = None
    qr_b64 = None
    if not existing:
        pending_device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
        if not pending_device:
            pending_device = TOTPDevice.objects.create(
                user=request.user, name=f"{request.user.username}-totp", confirmed=False
            )
        img = qrcode.make(pending_device.config_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render(request, "security/setup_2fa.html", {
        "active_nav": "security",
        "existing_device": existing,
        "pending_device": pending_device,
        "qr_b64": qr_b64,
    })


@login_required
def remove_2fa(request):
    if request.method == "POST":
        TOTPDevice.objects.filter(user=request.user).delete()
        messages.success(request, "Two-factor authentication has been removed from your account.")
    return redirect("setup_2fa")
