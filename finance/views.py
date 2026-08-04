from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.utils import get_user_tenant
from .models import Invoice, InvoiceFollowUp


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

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "action_followup":
            from crm.models import add_working_days
            followup_id = request.POST.get("followup_id")
            followup = get_object_or_404(InvoiceFollowUp, pk=followup_id, invoice=invoice, tenant=tenant)
            followup.outcome_notes = request.POST.get("outcome_notes", "").strip()
            followup.status = "done"
            followup.actioned_by = request.user
            followup.actioned_at = timezone.now()
            followup.save()

            closed_statuses = ["paid", "cancelled", "written_off"]
            if invoice.status not in closed_statuses:
                InvoiceFollowUp.objects.create(
                    tenant=tenant, invoice=invoice, follow_up_number=followup.follow_up_number + 1,
                    due_date=add_working_days(timezone.now().date(), 7),
                )

        elif action == "increment_reminder":
            invoice.xero_reminders_sent += 1
            invoice.save()

        elif action == "toggle_statement":
            invoice.statement_sent = not invoice.statement_sent
            invoice.save()

        return redirect("invoice_detail", pk=invoice.pk)

    return render(request, "finance/invoice_detail.html", {
        "active_nav": "finance",
        "user_tenant": tenant,
        "invoice": invoice,
        "payments": invoice.payments.order_by("-payment_date"),
        "follow_ups": invoice.follow_ups.all(),
    })
