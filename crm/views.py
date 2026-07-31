from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from tenants.utils import get_user_tenant
from .models import Organisation


@login_required
def organisation_list(request):
    tenant = get_user_tenant(request)
    orgs = Organisation.objects.filter(tenant=tenant) if tenant else Organisation.objects.none()

    q = request.GET.get("q", "").strip()
    if q:
        orgs = orgs.filter(legal_name__icontains=q)

    orgs = orgs.order_by("legal_name")

    return render(request, "crm/organisation_list.html", {
        "active_nav": "organisations",
        "user_tenant": tenant,
        "organisations": orgs,
        "q": q,
    })


@login_required
def organisation_detail(request, pk):
    tenant = get_user_tenant(request)
    org = get_object_or_404(Organisation, pk=pk, tenant=tenant)

    tab = request.GET.get("tab", "overview")

    return render(request, "crm/organisation_detail.html", {
        "active_nav": "organisations",
        "user_tenant": tenant,
        "org": org,
        "tab": tab,
        "contacts": org.contacts.all() if tab == "contacts" else None,
        "enquiries": org.enquiries.all() if tab == "enquiries" else None,
        "proposals": org.proposals.all() if tab == "proposals" else None,
        "projects": org.projects.all() if tab == "projects" else None,
    })
