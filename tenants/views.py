from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import Modality, Team, UserProfile
from .utils import get_user_tenant, is_tenant_admin


def tenant_admin_required(view_func):
    """Gate for the Manage area. Anyone who isn't a Tenant Admin (or
    superuser) gets bounced back to the Command Centre with a message,
    same pattern as `can_view_financials` elsewhere in the app."""

    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not is_tenant_admin(request.user):
            messages.error(request, "You don't have permission to manage this area.")
            return redirect("command_centre")
        return view_func(request, *args, **kwargs)

    return wrapped


# ---------------------------------------------------------------- home

@tenant_admin_required
def manage_home(request):
    tenant = get_user_tenant(request)
    return render(request, "tenants/manage_home.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "user_count": User.objects.filter(profile__tenant=tenant).count() if tenant else 0,
        "team_count": Team.objects.filter(tenant=tenant).count() if tenant else 0,
        "modality_count": Modality.objects.filter(tenant=tenant).count() if tenant else 0,
    })


# --------------------------------------------------------------- users

@tenant_admin_required
def manage_user_list(request):
    tenant = get_user_tenant(request)
    users = User.objects.filter(profile__tenant=tenant).select_related("profile") if tenant else User.objects.none()

    q = request.GET.get("q", "").strip()
    if q:
        users = users.filter(username__icontains=q) | users.filter(email__icontains=q)

    users = users.order_by("username")

    return render(request, "tenants/manage_user_list.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "users": users,
        "q": q,
    })


def _sync_user_teams(user, tenant, team_ids):
    """A user doesn't hold its teams directly - Team.members is the
    owning side of the relation - so saving a user's team list means
    adding it to the chosen teams and removing it from every other
    team in the tenant."""
    team_ids = set(team_ids)
    for team in Team.objects.filter(tenant=tenant):
        if team.id in team_ids:
            team.members.add(user)
        else:
            team.members.remove(user)


def _ensure_user_2fa(user, enable_2fa):
    """Create a pending TOTP device when an admin enables 2FA setup for a user."""
    if not enable_2fa:
        return False
    if TOTPDevice.objects.filter(user=user).exists():
        return False
    TOTPDevice.objects.create(user=user, name=f"{user.username}-totp", confirmed=False)
    return True


@tenant_admin_required
def manage_user_create(request):
    tenant = get_user_tenant(request)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        password = request.POST.get("password", "")
        role = request.POST.get("role", "")
        make_tenant_admin = request.POST.get("is_tenant_admin") == "on"
        enable_2fa = request.POST.get("enable_2fa") == "on"
        team_ids = [int(x) for x in request.POST.getlist("teams")]

        errors = []
        if not username:
            errors.append("Username is required.")
        elif User.objects.filter(username=username).exists():
            errors.append("That username is already taken.")
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters.")

        if not errors:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.tenant = tenant
            profile.role = role
            profile.is_tenant_admin = make_tenant_admin
            profile.save()
            _sync_user_teams(user, tenant, team_ids)
            enabled_2fa = _ensure_user_2fa(user, enable_2fa)
            if enabled_2fa:
                messages.success(request, f"{username} has been added and 2FA setup is now enabled for them.")
            else:
                messages.success(request, f"{username} has been added.")
            return redirect("manage_user_list")

        for e in errors:
            messages.error(request, e)

    teams = Team.objects.filter(tenant=tenant).order_by("name") if tenant else Team.objects.none()
    return render(request, "tenants/manage_user_form.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "is_new": True,
        "target_user": None,
        "teams": teams,
        "selected_team_ids": [],
        "role_choices": UserProfile.ROLE_CHOICES,
        "form_values": request.POST if request.method == "POST" else {},
    })


@tenant_admin_required
def manage_user_edit(request, pk):
    tenant = get_user_tenant(request)
    target_user = get_object_or_404(User.objects.select_related("profile"), pk=pk, profile__tenant=tenant)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    if request.method == "POST":
        action = request.POST.get("action", "save")

        if action == "toggle_active":
            target_user.is_active = not target_user.is_active
            target_user.save()
            messages.success(
                request,
                f"{target_user.username} has been {'reactivated' if target_user.is_active else 'deactivated'}.",
            )
            return redirect("manage_user_edit", pk=target_user.pk)

        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        role = request.POST.get("role", "")
        make_tenant_admin = request.POST.get("is_tenant_admin") == "on"
        team_ids = [int(x) for x in request.POST.getlist("teams")]
        new_password = request.POST.get("password", "").strip()

        if new_password and len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters - leave it blank to keep the current one.")
        else:
            target_user.email = email
            target_user.first_name = first_name
            target_user.last_name = last_name
            if new_password:
                target_user.set_password(new_password)
            target_user.save()

            profile.role = role
            profile.is_tenant_admin = make_tenant_admin
            profile.save()
            _sync_user_teams(target_user, tenant, team_ids)

            messages.success(request, f"{target_user.username} has been updated.")
            return redirect("manage_user_list")

    teams = Team.objects.filter(tenant=tenant).order_by("name") if tenant else Team.objects.none()
    selected_team_ids = list(target_user.teams.filter(tenant=tenant).values_list("id", flat=True))

    return render(request, "tenants/manage_user_form.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "is_new": False,
        "target_user": target_user,
        "profile": profile,
        "teams": teams,
        "selected_team_ids": selected_team_ids,
        "role_choices": UserProfile.ROLE_CHOICES,
        "form_values": {},
    })


# --------------------------------------------------------------- teams

@tenant_admin_required
def manage_team_list(request):
    tenant = get_user_tenant(request)
    teams = Team.objects.filter(tenant=tenant).prefetch_related("members", "modalities").order_by("name") if tenant else Team.objects.none()
    return render(request, "tenants/manage_team_list.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "teams": teams,
    })


def _save_team_from_post(request, tenant, team):
    team.name = request.POST.get("name", "").strip()
    team.tenant = tenant
    team.save()
    member_ids = [int(x) for x in request.POST.getlist("members")]
    modality_ids = [int(x) for x in request.POST.getlist("modalities")]
    team.members.set(User.objects.filter(id__in=member_ids, profile__tenant=tenant))
    team.modalities.set(Modality.objects.filter(id__in=modality_ids, tenant=tenant))


@tenant_admin_required
def manage_team_create(request):
    tenant = get_user_tenant(request)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Team name is required.")
        else:
            team = Team()
            _save_team_from_post(request, tenant, team)
            messages.success(request, f"{team.name} has been created.")
            return redirect("manage_team_list")

    return render(request, "tenants/manage_team_form.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "is_new": True,
        "team": None,
        "available_users": User.objects.filter(profile__tenant=tenant).order_by("username") if tenant else User.objects.none(),
        "available_modalities": Modality.objects.filter(tenant=tenant).order_by("name") if tenant else Modality.objects.none(),
        "selected_member_ids": [],
        "selected_modality_ids": [],
    })


@tenant_admin_required
def manage_team_edit(request, pk):
    tenant = get_user_tenant(request)
    team = get_object_or_404(Team, pk=pk, tenant=tenant)

    if request.method == "POST":
        if request.POST.get("action") == "delete":
            name = team.name
            team.delete()
            messages.success(request, f"{name} has been deleted.")
            return redirect("manage_team_list")

        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Team name is required.")
        else:
            _save_team_from_post(request, tenant, team)
            messages.success(request, f"{team.name} has been updated.")
            return redirect("manage_team_list")

    return render(request, "tenants/manage_team_form.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "is_new": False,
        "team": team,
        "available_users": User.objects.filter(profile__tenant=tenant).order_by("username") if tenant else User.objects.none(),
        "available_modalities": Modality.objects.filter(tenant=tenant).order_by("name") if tenant else Modality.objects.none(),
        "selected_member_ids": list(team.members.values_list("id", flat=True)),
        "selected_modality_ids": list(team.modalities.values_list("id", flat=True)),
    })


# ----------------------------------------------------------- modalities

@tenant_admin_required
def manage_modality_list(request):
    tenant = get_user_tenant(request)
    modalities = Modality.objects.filter(tenant=tenant).order_by("name") if tenant else Modality.objects.none()
    return render(request, "tenants/manage_modality_list.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "modalities": modalities,
    })


@tenant_admin_required
def manage_modality_create(request):
    tenant = get_user_tenant(request)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        if not name:
            messages.error(request, "Modality name is required.")
        else:
            Modality.objects.create(tenant=tenant, name=name, code=code)
            messages.success(request, f"{name} has been added.")
            return redirect("manage_modality_list")

    return render(request, "tenants/manage_modality_form.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "is_new": True,
        "modality": None,
    })


@tenant_admin_required
def manage_modality_edit(request, pk):
    tenant = get_user_tenant(request)
    modality = get_object_or_404(Modality, pk=pk, tenant=tenant)

    projects_using_it = modality.projects.count()

    if request.method == "POST":
        if request.POST.get("action") == "delete":
            if projects_using_it:
                messages.error(
                    request,
                    f"Can't delete {modality.name} - it's used on {projects_using_it} project(s). "
                    "Remove it from those projects first.",
                )
                return redirect("manage_modality_edit", pk=modality.pk)
            name = modality.name
            modality.delete()
            messages.success(request, f"{name} has been deleted.")
            return redirect("manage_modality_list")

        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        if not name:
            messages.error(request, "Modality name is required.")
        else:
            modality.name = name
            modality.code = code
            modality.save()
            messages.success(request, f"{modality.name} has been updated.")
            return redirect("manage_modality_list")

    return render(request, "tenants/manage_modality_form.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "is_new": False,
        "modality": modality,
        "projects_using_it": projects_using_it,
    })
