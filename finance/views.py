from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.utils import get_user_tenant, can_view_financials
from delivery.models import Milestone
from .models import Invoice, InvoiceFollowUp


@login_required
def invoice_create(request, milestone_pk):
    tenant = get_user_tenant(request)
    milestone = get_object_or_404(Milestone.objects.select_related("project"), pk=milestone_pk, tenant=tenant)
    project = milestone.project
    TAX_RATE = 0.10  # Australian GST

    can_create = can_view_financials(request.user) or request.user.id in (
        project.project_manager_id, project.director_id
    )
    if not can_create:
        messages.error(request, "You don't have permission to create invoices for this project.")
        return redirect("milestone_detail", pk=milestone.pk)

    if request.method == "POST":
        amount = request.POST.get("amount_excl_tax", "").strip()
        try:
            amount_val = round(float(amount), 2)
        except ValueError:
            messages.error(request, "Enter a valid amount.")
            return redirect("invoice_create", milestone_pk=milestone.pk)

        tax_val = round(amount_val * TAX_RATE, 2)
        total_val = amount_val + tax_val

        number = f"{project.project_number}-INV{project.invoices.count() + 1}"
        while Invoice.objects.filter(invoice_number=number).exists():
            number += "X"

        invoice = Invoice.objects.create(
            tenant=tenant, invoice_number=number, project=project,
            organisation=project.client_organisation, milestone=milestone,
            amount_excl_tax=amount_val, tax=tax_val, total=total_val,
            status="draft",
            due_date=request.POST.get("due_date") or None,
            notes=request.POST.get("notes", "").strip(),
        )
        messages.success(request, f"Invoice {invoice.invoice_number} saved as a draft. Review it, then mark it Issued.")
        return redirect("invoice_detail", pk=invoice.pk)

    suggested_amount = milestone.still_to_invoice or milestone.stage_value or 0
    total_fee = project.original_proposal.fee_amount if project.original_proposal_id else None
    return render(request, "finance/invoice_create.html", {
        "active_nav": "invoices",
        "user_tenant": tenant,
        "milestone": milestone,
        "project": project,
        "suggested_amount": suggested_amount,
        "total_fee": total_fee,
        "suggested_percentage": milestone.payment_percentage,
        "tax_rate_percent": TAX_RATE * 100,
    })


@login_required
def invoice_list(request):
    if not can_view_financials(request.user):
        messages.error(request, "You don't have permission to view financial information.")
        return redirect("command_centre")

    tenant = get_user_tenant(request)
    invoices = Invoice.objects.filter(tenant=tenant) if tenant else Invoice.objects.none()

    q = request.GET.get("q", "").strip()
    if q:
        invoices = invoices.filter(invoice_number__icontains=q) | invoices.filter(
            organisation__legal_name__icontains=q
        )

    status = request.GET.get("status", "").strip()
    if status:
        invoices = invoices.filter(status__in=status.split(","))

    today = timezone.localtime(timezone.now()).date()
    month = request.GET.get("month", "").strip()
    if month == "this":
        invoices = invoices.filter(invoice_date__year=today.year, invoice_date__month=today.month)

    followup = request.GET.get("followup", "").strip()
    if followup == "scheduled":
        invoices = invoices.filter(follow_ups__status="scheduled", follow_ups__due_date__gte=today).distinct()

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
    if not can_view_financials(request.user):
        messages.error(request, "You don't have permission to view financial information.")
        return redirect("command_centre")

    tenant = get_user_tenant(request)
    invoice = get_object_or_404(
        Invoice.objects.select_related("organisation", "project", "milestone"),
        pk=pk, tenant=tenant,
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "mark_issued":
            if invoice.status != "draft":
                messages.error(request, "Only draft invoices can be marked Issued this way.")
            else:
                invoice.status = "issued"
                invoice.invoice_date = invoice.invoice_date or timezone.localtime(timezone.now()).date()
                invoice.save()
                messages.success(request, f"Invoice {invoice.invoice_number} marked as Issued.")
            return redirect("invoice_detail", pk=invoice.pk)

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
