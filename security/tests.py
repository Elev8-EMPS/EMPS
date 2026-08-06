from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from security.trusted_device import COOKIE_NAME


class Verify2FATest(TestCase):
    @override_settings(TRUSTED_DEVICE_HOURS=24)
    def test_trust_device_checkbox_sets_cookie(self):
        user = get_user_model().objects.create_user(username="tester", password="pass1234")
        self.client.force_login(user)

        with patch("security.views.otp_login", return_value=None), patch("django_otp.match_token", return_value=object()):
            response = self.client.post(
                reverse("verify_2fa"),
                {"token": "123456", "next": "/", "trust_device": "on"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn(COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[COOKIE_NAME].max_age, 24 * 3600)

    def test_trust_device_checkbox_is_optional(self):
        user = get_user_model().objects.create_user(username="tester2", password="pass1234")
        self.client.force_login(user)

        with patch("security.views.otp_login", return_value=None), patch("django_otp.match_token", return_value=object()):
            response = self.client.post(
                reverse("verify_2fa"),
                {"token": "123456", "next": "/"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn(COOKIE_NAME, response.cookies)
