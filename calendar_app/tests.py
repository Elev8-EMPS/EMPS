from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from delivery.models import Milestone, Project, Task
from crm.models import Organisation
from tenants.models import Modality, Team, Tenant, UserProfile

from .models import CalendarPreference, LeaveApproval, LeaveRequest, LeaveType, PublicHoliday, WFHChangeRequest, WFHSchedule
from .services import find_approver, get_scope_codes, grouped_deadlines, process_approval_escalations, validate_wfh_change, wfh_users_on_date


class CalendarBaseTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Engineering")
        self.director = self._user("director", "director")
        self.manager = self._user("manager", "project_manager")
        self.employee = self._user("employee", "engineer")
        self.admin = self._user("admin", "company_admin")
        self.employee.profile.direct_manager = self.manager
        self.employee.profile.save()
        self.team = Team.objects.create(tenant=self.tenant, name="Electrical", manager=self.manager)
        self.team.members.add(self.manager, self.employee)
        self.modality = Modality.objects.create(tenant=self.tenant, name="Electrical", code="E")
        self.team.modalities.add(self.modality)
        self.employee.profile.modalities.add(self.modality)
        self.leave_type = LeaveType.objects.create(tenant=self.tenant, name="Annual Leave", code="annual")
        WFHSchedule.objects.create(tenant=self.tenant, user=self.employee, tuesday=True, thursday=True)

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password="StrongPassword123!")
        user.profile.tenant = self.tenant
        user.profile.role = role
        user.profile.save()
        return user


class LeaveWorkflowTests(CalendarBaseTest):
    def test_half_day_duration(self):
        request = LeaveRequest(
            tenant=self.tenant, requester=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), start_part="am", end_part="am",
        )
        request.full_clean()
        self.assertEqual(request.working_days, 0.5)

    def test_public_holiday_is_not_counted_as_leave_day(self):
        PublicHoliday.objects.create(tenant=self.tenant, date=date(2026, 8, 11), name="Test holiday")
        request = LeaveRequest(
            tenant=self.tenant, requester=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 12),
        )
        request.full_clean()
        self.assertEqual(request.working_days, 2)

    def test_multi_day_half_day_duration(self):
        request = LeaveRequest(
            tenant=self.tenant, requester=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 14), start_part="pm", end_part="am",
        )
        request.full_clean()
        self.assertEqual(request.working_days, 4)

    def test_manager_is_default_approver(self):
        approver = find_approver(self.employee, date(2026, 8, 10), date(2026, 8, 10))
        self.assertEqual(approver, self.manager)

    def test_leave_submission_creates_approval_task(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse("leave_request_create"), {
            "leave_type": self.leave_type.pk,
            "start_date": "2026-08-10", "end_date": "2026-08-10",
            "start_part": "full", "end_part": "full", "reason": "Family event",
        })
        self.assertRedirects(response, reverse("calendar_home"))
        leave = LeaveRequest.objects.get(requester=self.employee)
        self.assertEqual(leave.current_approver, self.manager)
        self.assertTrue(Task.objects.filter(owner=self.manager, description__icontains=f"Leave request #{leave.pk}").exists())

    def test_manager_can_approve(self):
        leave = LeaveRequest.objects.create(
            tenant=self.tenant, requester=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), current_approver=self.manager,
        )
        self.client.force_login(self.manager)
        response = self.client.post(reverse("leave_approve", args=[leave.pk]), {"action": "approve"})
        self.assertRedirects(response, reverse("leave_approval_list"))
        leave.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertTrue(LeaveApproval.objects.filter(request=leave, approver=self.manager, action="approved").exists())

    def test_decline_requires_reason(self):
        leave = LeaveRequest.objects.create(
            tenant=self.tenant, requester=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), current_approver=self.manager,
        )
        self.client.force_login(self.manager)
        self.client.post(reverse("leave_approve", args=[leave.pk]), {"action": "decline", "decline_reason": ""})
        leave.refresh_from_db()
        self.assertEqual(leave.status, "pending")
        self.client.post(reverse("leave_approve", args=[leave.pk]), {"action": "decline", "decline_reason": "Project deadline coverage"})
        leave.refresh_from_db()
        self.assertEqual(leave.status, "declined")
        self.assertEqual(leave.decline_reason, "Project deadline coverage")

    def test_employee_cannot_see_other_person_decline_reason(self):
        other = User.objects.create_user(username="other", password="StrongPassword123!")
        other.profile.tenant = self.tenant
        other.profile.role = "engineer"
        other.profile.save()
        leave = LeaveRequest.objects.create(
            tenant=self.tenant, requester=other, leave_type=self.leave_type,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), status="declined", decline_reason="Private reason",
        )
        self.client.force_login(self.employee)
        response = self.client.get(reverse("my_requests"))
        self.assertNotContains(response, "Private reason")
        self.assertContains(response, "No leave requests")

    def test_admin_can_approve_any_pending_leave(self):
        leave = LeaveRequest.objects.create(
            tenant=self.tenant, requester=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), current_approver=self.manager,
        )
        self.client.force_login(self.admin)
        response = self.client.post(reverse("leave_approve", args=[leave.pk]), {"action": "approve"})
        self.assertRedirects(response, reverse("leave_approval_list"))
        leave.refresh_from_db()
        self.assertEqual(leave.status, "approved")


class WFHTests(CalendarBaseTest):
    def test_swap_is_valid_only_when_original_is_recurring(self):
        obj = WFHChangeRequest(
            tenant=self.tenant, requester=self.employee, change_type="swap",
            original_date=date(2026, 8, 11), requested_date=date(2026, 8, 12),
        )
        with self.assertRaises(ValueError):
            validate_wfh_change(obj)

    def test_approved_wfh_swap_changes_effective_day(self):
        WFHChangeRequest.objects.create(
            tenant=self.tenant, requester=self.employee, change_type="swap",
            original_date=date(2026, 8, 11), requested_date=date(2026, 8, 12), status="approved",
        )
        tuesday = wfh_users_on_date(self.employee, self.tenant, date(2026, 8, 11))
        wednesday = wfh_users_on_date(self.employee, self.tenant, date(2026, 8, 12))
        self.assertNotIn(self.employee, tuesday)
        self.assertIn(self.employee, wednesday)

    def test_swap_can_be_submitted(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse("wfh_request_create"), {
            "change_type": "swap", "original_date": "2026-08-11", "requested_date": "2026-08-12", "reason": "Site meeting",
        })
        self.assertRedirects(response, reverse("calendar_home"))
        obj = WFHChangeRequest.objects.get(requester=self.employee)
        self.assertEqual(obj.current_approver, self.manager)


class CalendarVisibilityTests(CalendarBaseTest):
    def test_deadlines_are_grouped_with_scope_code(self):
        org = Organisation.objects.create(tenant=self.tenant, legal_name="Client")
        project = Project.objects.create(tenant=self.tenant, project_number="P10001", name="Project", client_organisation=org, project_manager=self.manager, status="active")
        project.modalities.add(self.modality)
        mechanical = Modality.objects.create(tenant=self.tenant, name="Mechanical", code="M")
        project.modalities.add(mechanical)
        m1 = Milestone.objects.create(tenant=self.tenant, project=project, milestone_type="Building Permit Issue", deadline=date(2026, 8, 20), responsible_user=self.manager)
        m1.modalities.add(self.modality)
        m2 = Milestone.objects.create(tenant=self.tenant, project=project, milestone_type="Building Permit Issue", deadline=date(2026, 8, 20))
        m2.modalities.add(mechanical)
        items = grouped_deadlines(self.manager, self.tenant, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["scope"], "E + M")
        self.assertTrue(items[0]["requires_action"])

    def test_employee_sees_team_leave_but_not_unrelated_leave(self):
        unrelated = User.objects.create_user(username="unrelated", password="StrongPassword123!")
        unrelated.profile.tenant = self.tenant
        unrelated.profile.role = "engineer"
        unrelated.profile.save()
        LeaveRequest.objects.create(tenant=self.tenant, requester=self.employee, leave_type=self.leave_type, start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), status="approved")
        LeaveRequest.objects.create(tenant=self.tenant, requester=unrelated, leave_type=self.leave_type, start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), status="approved")
        from .services import visible_leave_requests
        visible = visible_leave_requests(self.employee, self.tenant, date(2026, 8, 10), date(2026, 8, 10))
        self.assertIn(self.employee, [x.requester for x in visible])
        self.assertNotIn(unrelated, [x.requester for x in visible])

    def test_employee_cannot_access_management_hub(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("management_hub"))
        self.assertEqual(response.status_code, 404)

    def test_manager_can_access_management_hub(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("management_hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "employee")

    def test_tenant_isolation_for_calendar(self):
        other_tenant = Tenant.objects.create(name="Other Company")
        other_user = User.objects.create_user(username="other-tenant", password="StrongPassword123!")
        other_user.profile.tenant = other_tenant
        other_user.profile.role = "engineer"
        other_user.profile.save()
        LeaveType.objects.create(tenant=other_tenant, name="Annual", code="annual")
        self.client.force_login(self.employee)
        response = self.client.get(reverse("calendar_home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Other Company")


class EscalationTests(CalendarBaseTest):
    def test_stale_approval_creates_admin_task(self):
        leave = LeaveRequest.objects.create(
            tenant=self.tenant, requester=self.employee, leave_type=self.leave_type,
            start_date=date(2026, 8, 10), end_date=date(2026, 8, 10), current_approver=self.manager,
        )
        leave.submitted_at = timezone.now() - timedelta(days=10)
        leave.save(update_fields=["submitted_at", "updated_at"])
        created = process_approval_escalations(self.tenant)
        self.assertGreaterEqual(created, 1)
        self.assertTrue(Task.objects.filter(owner=self.admin, title=f"Approval escalation #{leave.pk}").exists())
