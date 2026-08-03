from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from tenants.utils import get_user_tenant
from .models import Invoice


@login_required
def invoice_list(request):
    tenant = get_user_tenant(request)
    invoices = Invoice.objects.filter(tenant=tenant) if tenant else Invoice.objects.none()

    q = request.GET.get("q", "").strip()
    if q:
        invoices = invoices.filter(invoice_number__icontains=q) | invoices.filter(
            organisation__legal_name__icontains=q
        )

    status = request.GET.get("status", "").strip()
    if status:
        invoices = invoices.filter(status=status)

    invoices = invoices.select_related("organisation", "project").order_by("-due_date", "invoice_number")

    return render(request, "finance/invoice_list.html", {
        "active_nav": "finance",
        "user_tenant": tenant,
        "invoices": invoices,
        "q": q,
        "status": status,
        "status_choices": Invoice.STATUS_CHOICES,
    })


@login_required
def invoice_detail(request, pk):
    tenant = get_user_tenant(request)
    invoice = get_object_or_404(
        Invoice.objects.select_related("organisation", "project", "milestone"),
        pk=pk, tenant=tenant,
    )
    return render(request, "finance/invoice_detail.html", {
        "active_nav": "finance",
        "user_tenant": tenant,
        "invoice": invoice,
        "payments": invoice.payments.order_by("-payment_date"),
    })
