from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from tenants.utils import get_user_tenant, can_view_financials, can_edit_financials, has_company_wide_scope
from delivery.models import Milestone
from .models import Invoice, InvoiceFollowUp, Payment


@login_required
def invoice_create(request, milestone_pk):
    tenant = get_user_tenant(request)
    milestone = get_object_or_404(Milestone.objects.select_related("project"), pk=milestone_pk, tenant=tenant)
    project = milestone.project
    TAX_RATE = 0.10  # Australian GST

    can_create = can_edit_financials(request.user) or request.user.id in (
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
        if not can_edit_financials(request.user):
            messages.error(request, "Your financial access is view-only - you can't make changes to invoices.")
            return redirect("invoice_detail", pk=invoice.pk)

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

        if action == "add_payment":
            if invoice.status == "draft":
                messages.error(request, "Mark the invoice Issued before recording a payment against it.")
                return redirect("invoice_detail", pk=invoice.pk)

            amount = request.POST.get("payment_amount", "").strip()
            try:
                amount_val = round(float(amount), 2)
                assert amount_val > 0
            except (ValueError, AssertionError):
                messages.error(request, "Enter a valid payment amount.")
                return redirect("invoice_detail", pk=invoice.pk)

            Payment.objects.create(
                tenant=tenant, invoice=invoice,
                payment_date=request.POST.get("payment_date") or timezone.localtime(timezone.now()).date(),
                amount=amount_val,
                method=request.POST.get("payment_method", "").strip(),
                reference=request.POST.get("payment_reference", "").strip(),
            )

            from django.db.models import Sum
            paid_total = invoice.payments.aggregate(total=Sum("amount"))["total"] or 0
            invoice.amount_paid = paid_total
            if paid_total >= invoice.total:
                invoice.status = "paid"
            elif paid_total > 0:
                invoice.status = "part_paid"
            invoice.save()

            messages.success(request, f"Payment of ${amount_val} recorded.")
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


UNPAID_STATUSES = ["awaiting_approval", "approved", "issued", "part_paid", "overdue", "disputed"]
INVOICED_TOTAL_STATUSES = ["awaiting_approval", "approved", "issued", "part_paid", "overdue", "disputed", "paid"]
MONTHLY_TARGET = 175000


@login_required
def wip_dashboard(request):
    """The company-wide WIP + Aged Debtor screen - deliberately
    Director/Company Admin only, per the requirement that this level
    of visibility across every project's financials is restricted
    beyond the general Financials view/edit permission."""
    if not has_company_wide_scope(request.user):
        messages.error(request, "The WIP dashboard is restricted to Directors and Company Admin.")
        return redirect("command_centre")

    tenant = get_user_tenant(request)
    today = timezone.localtime(timezone.now()).date()

    # --- Aged debtor buckets ---
    outstanding_invoices = Invoice.objects.filter(
        tenant=tenant, status__in=UNPAID_STATUSES
    ).select_related("organisation", "project")

    buckets = {"current": [], "b1": [], "b2": [], "b3": []}
    bucket_totals = {"current": 0, "b1": 0, "b2": 0, "b3": 0}
    for inv in outstanding_invoices:
        reference_date = inv.due_date or inv.invoice_date
        days_overdue = (today - reference_date).days if reference_date else 0
        if days_overdue <= 30:
            key = "current"
        elif days_overdue <= 60:
            key = "b1"
        elif days_overdue <= 90:
            key = "b2"
        else:
            key = "b3"
        buckets[key].append(inv)
        bucket_totals[key] += inv.outstanding_amount

    total_outstanding = sum(bucket_totals.values())

    # --- This month's invoiced vs paid, against the monthly target ---
    invoiced_this_month = Invoice.objects.filter(
        tenant=tenant, status__in=INVOICED_TOTAL_STATUSES,
        invoice_date__year=today.year, invoice_date__month=today.month,
    ).aggregate(total=Sum("total"))["total"] or 0
    paid_this_month = Payment.objects.filter(
        tenant=tenant, payment_date__year=today.year, payment_date__month=today.month,
    ).aggregate(total=Sum("amount"))["total"] or 0

    # --- Per-project WIP: total fee vs invoiced vs outstanding ---
    from delivery.models import Project
    projects = Project.objects.filter(tenant=tenant, status="active").select_related(
        "client_organisation", "original_proposal"
    )
    wip_rows = []
    for p in projects:
        total_fee = p.original_proposal.fee_amount if p.original_proposal_id else p.original_fee
        invoiced = p.invoices.filter(status__in=INVOICED_TOTAL_STATUSES).aggregate(total=Sum("total"))["total"] or 0
        outstanding = p.invoices.filter(status__in=UNPAID_STATUSES).aggregate(
            total=Sum("total") - Sum("amount_paid")
        )["total"] or 0
        wip_rows.append({
            "project": p,
            "total_fee": total_fee or 0,
            "invoiced": invoiced,
            "outstanding": outstanding,
            "percent_invoiced": round((invoiced / total_fee) * 100) if total_fee else None,
        })
    wip_rows.sort(key=lambda r: r["outstanding"], reverse=True)

    return render(request, "finance/wip_dashboard.html", {
        "active_nav": "wip",
        "user_tenant": tenant,
        "bucket_current": sorted(buckets["current"], key=lambda i: i.outstanding_amount, reverse=True),
        "bucket_b1": sorted(buckets["b1"], key=lambda i: i.outstanding_amount, reverse=True),
        "bucket_b2": sorted(buckets["b2"], key=lambda i: i.outstanding_amount, reverse=True),
        "bucket_b3": sorted(buckets["b3"], key=lambda i: i.outstanding_amount, reverse=True),
        "bucket_totals": bucket_totals,
        "total_outstanding": total_outstanding,
        "invoiced_this_month": invoiced_this_month,
        "paid_this_month": paid_this_month,
        "monthly_target": MONTHLY_TARGET,
        "invoiced_target_pct": min(round((invoiced_this_month / MONTHLY_TARGET) * 100), 100) if MONTHLY_TARGET else 0,
        "paid_target_pct": min(round((paid_this_month / MONTHLY_TARGET) * 100), 100) if MONTHLY_TARGET else 0,
        "wip_rows": wip_rows,
    })
