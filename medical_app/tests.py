from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    ChatMessage,
    FeaturedImage,
    LoginActivity,
    MedicalAnalysis,
    PendingRegistration,
    TreatmentEntry,
    UserProfile,
)

user_model = get_user_model()


class PublicPageTests(TestCase):
    def test_homepage_loads_featured_images(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quick Access")
        self.assertContains(response, "Important Notice")
        self.assertTrue(FeaturedImage.objects.exists())
        self.assertContains(response, "medical-assistant-logo.svg")

    def test_healthcheck_endpoint_returns_ok(self):
        response = self.client.get(reverse("healthcheck"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationTests(TestCase):
    def test_registration_page_exposes_live_validation_hooks(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-live-validate="email"')
        self.assertContains(response, 'data-live-validate="mobile"')
        self.assertContains(response, "medical-assistant-logo.svg")

    @patch("medical_app.verification.generate_otp_code", side_effect=["123456", "654321"])
    def test_registration_creates_profile_with_required_fields(self, mock_codes):
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

        pending = PendingRegistration.objects.get(email="ava@example.com")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verify your email and mobile OTP")
        self.assertFalse(user_model.objects.filter(email="ava@example.com").exists())
        self.assertEqual(len(mail.outbox), 1)

        verify_response = self.client.post(
            reverse("register_verify", args=[pending.verification_token]),
            {
                "email_otp": "123456",
                "mobile_otp": "654321",
            },
            follow=True,
        )

        user = user_model.objects.get(email="ava@example.com")

        self.assertEqual(verify_response.status_code, 200)
        self.assertEqual(user.first_name, "Ava")
        self.assertEqual(user.profile.mobile_number, "9876543210")
        self.assertFalse(PendingRegistration.objects.filter(email="ava@example.com").exists())

    def test_registration_rejects_invalid_email_and_mobile(self):
        response = self.client.post(
            reverse("register"),
            {
                "first_name": "Ava",
                "last_name": "Stone",
                "email": "invalid-email",
                "mobile_number": "98AB765",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email ID.")
        self.assertContains(response, "Enter a valid mobile number with 10 to 15 digits.")
        self.assertFalse(user_model.objects.filter(email="invalid-email").exists())

    @patch("medical_app.verification.generate_otp_code", side_effect=["123456", "654321"])
    def test_registration_does_not_complete_with_invalid_otp(self, mock_codes):
        self.client.post(
            reverse("register"),
            {
                "first_name": "Ava",
                "last_name": "Stone",
                "email": "ava@example.com",
                "mobile_number": "9876543210",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        pending = PendingRegistration.objects.get(email="ava@example.com")
        response = self.client.post(
            reverse("register_verify", args=[pending.verification_token]),
            {
                "email_otp": "111111",
                "mobile_otp": "222222",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The email OTP is incorrect.")
        self.assertContains(response, "The mobile OTP is incorrect.")
        self.assertFalse(user_model.objects.filter(email="ava@example.com").exists())


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


class ClinicalAnalysisTests(TestCase):
    def setUp(self):
        self.user = user_model.objects.create_user(
            username="doctor_user",
            email="doctor@example.com",
            first_name="Doctor",
            last_name="Tester",
            password="SecurePass123!",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"mobile_number": "9998887776"},
        )

    @patch("medical_app.views.text_to_speech_with_edge")
    @patch("medical_app.views.analyze_image_with_query", return_value="Structured clinical summary.")
    def test_index_post_creates_medical_analysis_record(self, mock_ai, mock_tts):
        self.client.login(username="doctor_user", password="SecurePass123!")

        response = self.client.post(
            reverse("index"),
            {
                "symptoms": "Persistent cough with mild fever for three days",
                "report_notes": "Inflammation markers are elevated.",
                "language": "english",
            },
            follow=True,
        )

        analysis = MedicalAnalysis.objects.get(user=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Latest Clinical Record Saved")
        self.assertEqual(analysis.predicted_condition, "Infection")
        self.assertEqual(analysis.risk_level, "Medium")
        self.assertEqual(analysis.ai_summary, "Structured clinical summary.")
        mock_tts.assert_called_once()

    def test_analysis_detail_requires_login(self):
        analysis = MedicalAnalysis.objects.create(
            user=self.user,
            title="Test Analysis",
            predicted_condition="General review required",
        )

        response = self.client.get(reverse("analysis_detail", args=[analysis.id]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_treatment_entry_can_be_created_updated_and_deleted(self):
        self.client.login(username="doctor_user", password="SecurePass123!")
        analysis = MedicalAnalysis.objects.create(
            user=self.user,
            title="Respiratory Review",
            predicted_condition="Respiratory",
            risk_level="Medium",
        )

        create_response = self.client.post(
            reverse("analysis_detail", args=[analysis.id]),
            {
                "doctor_name": "Dr. John Carter",
                "doctor_id": "DOC-101",
                "specialization": "Pulmonology",
                "contact_details": "555-1010",
                "treatment_notes": "Start inhaler support and review in 48 hours.",
            },
            follow=True,
        )

        treatment_entry = TreatmentEntry.objects.get(analysis=analysis)

        self.assertEqual(create_response.status_code, 200)
        self.assertContains(create_response, "Treatment entry saved successfully.")

        edit_response = self.client.post(
            reverse("treatment_entry_edit", args=[analysis.id, treatment_entry.id]),
            {
                "doctor_name": "Dr. John Carter",
                "doctor_id": "DOC-101",
                "specialization": "Pulmonology",
                "contact_details": "555-1010",
                "treatment_notes": "Updated follow-up after inhaler review.",
            },
            follow=True,
        )

        treatment_entry.refresh_from_db()
        self.assertEqual(edit_response.status_code, 200)
        self.assertEqual(treatment_entry.treatment_notes, "Updated follow-up after inhaler review.")

        delete_response = self.client.post(
            reverse("treatment_entry_delete", args=[analysis.id, treatment_entry.id]),
            follow=True,
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(TreatmentEntry.objects.filter(id=treatment_entry.id).exists())


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

    def test_account_settings_page_exposes_live_validation_hooks(self):
        self.client.login(username="patient_user", password="SecurePass123!")

        response = self.client.get(reverse("change_credentials"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-live-validate="email"')
        self.assertContains(response, 'data-live-validate="mobile"')

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

    def test_user_cannot_update_profile_with_invalid_email_or_mobile(self):
        self.client.login(username="patient_user", password="SecurePass123!")

        response = self.client.post(
            reverse("change_credentials"),
            {
                "form_type": "profile",
                "profile-first_name": "Patient",
                "profile-last_name": "User",
                "profile-email": "not-an-email",
                "profile-mobile_number": "12AB",
            },
        )

        self.user.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email ID.")
        self.assertContains(response, "Enter a valid mobile number with 10 to 15 digits.")
        self.assertEqual(self.user.email, "patient@example.com")
        self.assertEqual(self.user.profile.mobile_number, "8888888888")

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
