import logging
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from .models import Team, Modality, UserProfile, ChecklistItemTemplate, Tenant
from .utils import get_user_tenant, can_view_confidential

logger = logging.getLogger(__name__)


def _parse_date(value):
    """Parses an HTML date input (YYYY-MM-DD) into a date, or None if blank/invalid."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _require_admin(request):
    """Every view in this file is admin/director-only - this is where
    staff, teams, and modalities get managed, not day-to-day work."""
    if not can_view_confidential(request.user):
        messages.error(request, "You don't have permission to access the management area.")
        return redirect("command_centre")
    return None


@login_required
def manage_hub(request):
    denied = _require_admin(request)
    if denied:
        return denied

    tenant = get_user_tenant(request)
    tab = request.GET.get("tab", "users")

    if request.method == "POST" and tab == "settings":
        if tenant:
            visibility = request.POST.get("dashboard_visibility", "restricted")
            valid_values = {v for v, _ in Tenant.DASHBOARD_VISIBILITY_CHOICES}
            if visibility in valid_values:
                tenant.dashboard_visibility = visibility
                tenant.save()
                messages.success(request, "Settings saved.")
        return redirect("/manage/?tab=settings")

    return render(request, "tenants/manage_hub.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "tab": tab,
        "users": User.objects.filter(profile__tenant=tenant).select_related("profile").order_by("username") if tab == "users" else None,
        "teams": Team.objects.filter(tenant=tenant).order_by("name") if tab == "teams" else None,
        "modalities": Modality.objects.filter(tenant=tenant).order_by("name") if tab == "modalities" else None,
        "visibility_choices": Tenant.DASHBOARD_VISIBILITY_CHOICES if tab == "settings" else None,
    })


@login_required
def manage_user_create(request):
    denied = _require_admin(request)
    if denied:
        return denied

    tenant = get_user_tenant(request)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "").strip()
        role = request.POST.get("role", "")
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        date_of_birth = _parse_date(request.POST.get("date_of_birth"))
        date_started = _parse_date(request.POST.get("date_started"))
        manager_id = request.POST.get("manager") or None

        if username and password and not User.objects.filter(username=username).exists():
            try:
                with transaction.atomic():
                    user = User.objects.create_user(
                        username=username, email=email, password=password, is_staff=True,
                        first_name=first_name, last_name=last_name,
                    )
                    profile = UserProfile.objects.create(
                        user=user, tenant=tenant, role=role, manager_id=manager_id,
                        can_manage_proposals=request.POST.get("can_manage_proposals") == "on",
                        phone=phone, date_of_birth=date_of_birth, date_started=date_started,
                    )
                    team_ids = request.POST.getlist("teams")
                    if team_ids:
                        user.teams.set(team_ids)
                    modality_ids = request.POST.getlist("modalities")
                    if modality_ids:
                        profile.modalities.set(modality_ids)
                messages.success(request, f"Created account for {username}.")
                return redirect("manage_user_edit", pk=user.pk)
            except Exception:
                logger.exception("Failed to create user '%s' via Manage", username)
                messages.error(
                    request,
                    "Something went wrong creating that account - nothing was saved, so it's safe to try "
                    "again. If it keeps happening, let Claude know so it can check the error log.",
                )
        else:
            messages.error(request, "Username and password are required, and the username must be unique.")

    return render(request, "tenants/manage_user_create.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "role_choices": UserProfile.ROLE_CHOICES,
        "teams": Team.objects.filter(tenant=tenant).order_by("name"),
        "modalities": Modality.objects.filter(tenant=tenant).order_by("name"),
        "all_users": User.objects.filter(profile__tenant=tenant, is_active=True).order_by("username"),
    })


@login_required
def manage_user_edit(request, pk):
    denied = _require_admin(request)
    if denied:
        return denied

    tenant = get_user_tenant(request)
    target_user = get_object_or_404(User, pk=pk, profile__tenant=tenant)
    profile, _ = UserProfile.objects.get_or_create(user=target_user, defaults={"tenant": tenant})

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "update":
            try:
                with transaction.atomic():
                    profile.role = request.POST.get("role", "")
                    profile.can_manage_proposals = request.POST.get("can_manage_proposals") == "on"
                    profile.phone = request.POST.get("phone", "").strip()
                    profile.date_of_birth = _parse_date(request.POST.get("date_of_birth"))
                    profile.date_started = _parse_date(request.POST.get("date_started"))
                    manager_id = request.POST.get("manager") or None
                    if manager_id == str(target_user.pk):
                        messages.error(request, "Someone can't be their own manager - manager not changed.")
                    else:
                        profile.manager_id = manager_id
                    profile.save()
                    profile.modalities.set(request.POST.getlist("modalities"))
                    target_user.email = request.POST.get("email", "").strip()
                    target_user.first_name = request.POST.get("first_name", "").strip()
                    target_user.last_name = request.POST.get("last_name", "").strip()
                    target_user.teams.set(request.POST.getlist("teams"))
                    target_user.save()
                messages.success(request, f"Updated {target_user.username}.")
                return redirect("/manage/?tab=users")
            except Exception:
                logger.exception("Failed to update user '%s' via Manage", target_user.username)
                messages.error(request, "Something went wrong saving those changes - nothing was updated, try again.")

        elif action == "reset_password":
            new_password = request.POST.get("new_password", "").strip()
            if new_password:
                target_user.set_password(new_password)
                target_user.save()
                messages.success(request, "Password reset.")

        elif action == "toggle_active":
            target_user.is_active = not target_user.is_active
            target_user.save()
            state = "reactivated" if target_user.is_active else "deactivated (retired)"
            messages.success(request, f"Account {state}. Their history and past work are preserved.")

        return redirect("manage_user_edit", pk=target_user.pk)

    return render(request, "tenants/manage_user_edit.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "target_user": target_user,
        "profile": profile,
        "role_choices": UserProfile.ROLE_CHOICES,
        "teams": Team.objects.filter(tenant=tenant).order_by("name"),
        "my_team_ids": set(target_user.teams.values_list("id", flat=True)),
        "modalities": Modality.objects.filter(tenant=tenant).order_by("name"),
        "my_modality_ids": set(profile.modalities.values_list("id", flat=True)),
        "all_users": User.objects.filter(profile__tenant=tenant, is_active=True).exclude(pk=target_user.pk).order_by("username"),
    })


@login_required
def manage_team_create(request):
    denied = _require_admin(request)
    if denied:
        return denied
    tenant = get_user_tenant(request)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            try:
                with transaction.atomic():
                    team = Team.objects.create(tenant=tenant, name=name)
                    team.members.set(request.POST.getlist("members"))
                    team.modalities.set(request.POST.getlist("modalities"))
                messages.success(request, f"Created team '{name}'.")
                return redirect("manage_team_edit", pk=team.pk)
            except Exception:
                logger.exception("Failed to create team '%s' via Manage", name)
                messages.error(request, "Something went wrong creating that team - nothing was saved, try again.")

    return render(request, "tenants/manage_team_create.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "users": User.objects.filter(profile__tenant=tenant).order_by("username"),
        "modalities": Modality.objects.filter(tenant=tenant).order_by("name"),
    })


@login_required
def manage_team_edit(request, pk):
    denied = _require_admin(request)
    if denied:
        return denied
    tenant = get_user_tenant(request)
    team = get_object_or_404(Team, pk=pk, tenant=tenant)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update":
            try:
                with transaction.atomic():
                    team.name = request.POST.get("name", team.name).strip()
                    team.members.set(request.POST.getlist("members"))
                    team.modalities.set(request.POST.getlist("modalities"))
                    team.save()
                messages.success(request, "Team updated.")
            except Exception:
                logger.exception("Failed to update team '%s' via Manage", team.name)
                messages.error(request, "Something went wrong saving those changes - nothing was updated, try again.")
        elif action == "delete":
            team.delete()
            messages.success(request, "Team deleted.")
            return redirect("/manage/?tab=teams")
        return redirect("manage_team_edit", pk=team.pk)

    return render(request, "tenants/manage_team_edit.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "team": team,
        "users": User.objects.filter(profile__tenant=tenant).order_by("username"),
        "modalities": Modality.objects.filter(tenant=tenant).order_by("name"),
        "member_ids": set(team.members.values_list("id", flat=True)),
        "modality_ids": set(team.modalities.values_list("id", flat=True)),
    })


@login_required
def manage_modality_create(request):
    denied = _require_admin(request)
    if denied:
        return denied
    tenant = get_user_tenant(request)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip()
        if name:
            modality = Modality.objects.create(tenant=tenant, name=name, code=code)
            messages.success(request, f"Created modality '{name}'.")
            return redirect("manage_modality_edit", pk=modality.pk)

    return render(request, "tenants/manage_modality_create.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
    })


@login_required
def manage_modality_edit(request, pk):
    denied = _require_admin(request)
    if denied:
        return denied
    tenant = get_user_tenant(request)
    modality = get_object_or_404(Modality, pk=pk, tenant=tenant)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update":
            modality.name = request.POST.get("name", modality.name).strip()
            modality.code = request.POST.get("code", "").strip()
            modality.save()
            messages.success(request, "Modality updated.")
        elif action == "delete":
            modality.delete()
            messages.success(request, "Modality deleted.")
            return redirect("/manage/?tab=modalities")
        elif action == "add_checklist_item":
            text = request.POST.get("text", "").strip()
            if text:
                ChecklistItemTemplate.objects.create(
                    tenant=tenant, modality=modality, text=text,
                    always_included=request.POST.get("always_included") == "on",
                )
        elif action == "delete_checklist_item":
            ChecklistItemTemplate.objects.filter(id=request.POST.get("item_id"), tenant=tenant, modality=modality).delete()
        return redirect("manage_modality_edit", pk=modality.pk)

    return render(request, "tenants/manage_modality_edit.html", {
        "active_nav": "manage",
        "user_tenant": tenant,
        "modality": modality,
        "checklist_items": modality.checklist_templates.order_by("-always_included", "text"),
    })
