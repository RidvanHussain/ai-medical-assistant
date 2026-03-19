from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import ChatMessage, FeaturedImage, LoginActivity, UserProfile

user_model = get_user_model()


class PublicPageTests(TestCase):
    def test_homepage_loads_featured_images(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quick Access")
        self.assertTrue(FeaturedImage.objects.exists())


class RegistrationTests(TestCase):
    def test_registration_creates_profile_with_required_fields(self):
        response = self.client.post(
            reverse("register"),
            {
                "first_name": "Ava",
                "last_name": "Stone",
                "email": "ava@example.com",
                "mobile_number": "9876543210",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
            follow=True,
        )

        user = user_model.objects.get(email="ava@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(user.first_name, "Ava")
        self.assertEqual(user.profile.mobile_number, "9876543210")


class ChatTests(TestCase):
    def setUp(self):
        self.user = user_model.objects.create_user(
            username="clinician",
            email="clinician@example.com",
            password="SecurePass123!",
        )

    def test_chat_requires_login(self):
        response = self.client.get(reverse("chat"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    @patch("medical_app.views.analyze_image_with_query", return_value="Structured reply.")
    def test_chat_escapes_rendered_message_content(self, mock_ai):
        self.client.login(username="clinician", password="SecurePass123!")

        response = self.client.post(
            reverse("chat"),
            {"message": "<script>alert(1)</script>"},
            follow=True,
        )

        html = response.content.decode()

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertTrue(ChatMessage.objects.filter(role="assistant", text="Structured reply.").exists())


class DashboardTests(TestCase):
    def setUp(self):
        self.admin_user = user_model.objects.create_user(
            username="admin_user",
            email="admin_user@example.com",
            first_name="Admin",
            last_name="Manager",
            password="SecurePass123!",
            is_staff=True,
        )
        UserProfile.objects.update_or_create(
            user=self.admin_user,
            defaults={"mobile_number": "9999999999"},
        )
        LoginActivity.objects.create(
            user=self.admin_user,
            session_key="abc123",
            ip_address="127.0.0.1",
            location_label="Local development machine",
            device_name="Windows desktop",
            browser_name="Google Chrome",
            is_active=True,
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_staff_dashboard_shows_user_management(self):
        self.client.login(username="admin_user", password="SecurePass123!")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Management")
        self.assertContains(response, "Admin Manager")


class AccountSettingsTests(TestCase):
    def setUp(self):
        self.user = user_model.objects.create_user(
            username="patient_user",
            email="patient@example.com",
            first_name="Patient",
            last_name="User",
            password="SecurePass123!",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"mobile_number": "8888888888"},
        )

    def test_account_settings_requires_login(self):
        response = self.client.get(reverse("change_credentials"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_user_can_update_profile(self):
        self.client.login(username="patient_user", password="SecurePass123!")

        response = self.client.post(
            reverse("change_credentials"),
            {
                "form_type": "profile",
                "profile-first_name": "Updated",
                "profile-last_name": "Member",
                "profile-email": "updated@example.com",
                "profile-mobile_number": "7777777777",
            },
            follow=True,
        )

        self.user.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertEqual(self.user.profile.mobile_number, "7777777777")

    def test_user_can_update_password(self):
        self.client.login(username="patient_user", password="SecurePass123!")

        response = self.client.post(
            reverse("change_credentials"),
            {
                "form_type": "password",
                "password-old_password": "SecurePass123!",
                "password-new_password1": "NewSecurePass456!",
                "password-new_password2": "NewSecurePass456!",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            self.client.login(username="patient_user", password="NewSecurePass456!")
        )
