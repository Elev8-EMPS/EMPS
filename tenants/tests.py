from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Tenant, UserProfile


class ManageUserCreationTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.admin = self.user_model.objects.create_user(
            username="admin",
            password="secret1234",
            is_staff=True,
            is_superuser=True,
        )
        self.admin.profile.tenant = self.tenant
        self.admin.profile.is_tenant_admin = True
        self.admin.profile.save()

    def test_create_user_assigns_profile_and_redirects(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("manage_user_create"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password": "password123",
                "first_name": "New",
                "last_name": "User",
                "role": "",
                "is_tenant_admin": "on",
                "enable_2fa": "on",
                "teams": [],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse("manage_user_list"))

        created_user = self.user_model.objects.get(username="newuser")
        profile = UserProfile.objects.get(user=created_user)
        self.assertEqual(profile.tenant, self.tenant)
        self.assertTrue(profile.is_tenant_admin)
        self.assertTrue(created_user.is_active)
