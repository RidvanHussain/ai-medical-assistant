import uuid
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .analysis_engine import analyze_report_text
from .model_evaluation import load_evaluation_report
from .models import (
    ChatMessage,
    FeaturedImage,
    LoginActivity,
    MedicalAnalysis,
    PendingRegistration,
    TreatmentEntry,
    TreatmentTrainingRecord,
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
        self.member_user = user_model.objects.create_user(
            username="member_user",
            email="member@example.com",
            first_name="Member",
            last_name="Viewer",
            password="SecurePass123!",
        )
        UserProfile.objects.update_or_create(
            user=self.member_user,
            defaults={"mobile_number": "8887776665"},
        )
        self.patient_owner = user_model.objects.create_user(
            username="case_owner",
            email="case_owner@example.com",
            first_name="Case",
            last_name="Owner",
            password="SecurePass123!",
        )
        analysis = MedicalAnalysis.objects.create(
            user=self.patient_owner,
            title="Eye Comfort Review",
            predicted_condition="Visual review suggested",
            report_text="Eye redness and irritation were noted after dust exposure.",
            risk_level="Low",
        )
        TreatmentEntry.objects.create(
            analysis=analysis,
            doctor_name="Dr. Private Detail",
            doctor_id="DOC-909",
            specialization="Eye Specialist",
            contact_details="555-9090",
            treatment_notes=(
                "Rinse the eye gently with sterile saline and use lubricating drops twice daily. "
                "Avoid rubbing the eye and reduce screen exposure for the next 48 hours. "
                "Return for review if pain or discharge worsens."
            ),
            added_by=self.admin_user,
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

    def test_member_dashboard_shows_shared_treatment_summary_without_private_details(self):
        self.client.login(username="member_user", password="SecurePass123!")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Treatment Knowledge Feed")
        self.assertContains(response, "Eye Specialist")
        self.assertContains(response, "Rinse the eye gently with sterile saline")
        self.assertNotContains(response, "Dr. Private Detail")
        self.assertNotContains(response, "DOC-909")
        self.assertNotContains(response, "555-9090")


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

    @patch("medical_app.views.text_to_speech_with_edge")
    @patch("medical_app.views.analyze_image_with_query", return_value="Structured disease comparison summary.")
    def test_index_can_compare_previous_and_current_reports_with_percentage_chart(self, mock_ai, mock_tts):
        self.client.login(username="doctor_user", password="SecurePass123!")

        response = self.client.post(
            reverse("index"),
            {
                "report_notes": "Current report shows disease burden at 30% with improved response to treatment.",
                "previous_report_notes": "Previous report recorded disease burden at 80% before treatment was started.",
                "language": "english",
            },
            follow=True,
        )

        analysis = MedicalAnalysis.objects.get(user=self.user)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disease Burden Comparison")
        self.assertContains(response, "Reduced")
        self.assertContains(response, "Remaining")
        self.assertEqual(analysis.disease_percentage, 30.0)
        self.assertEqual(analysis.previous_disease_percentage, 80.0)
        self.assertEqual(analysis.percentage_reduced, 50.0)
        self.assertEqual(analysis.percentage_remaining, 30.0)
        self.assertEqual(analysis.progression_status, "Improved")
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
        training_record = TreatmentTrainingRecord.objects.get(treatment=treatment_entry)

        self.assertEqual(create_response.status_code, 200)
        self.assertContains(
            create_response,
            "Treatment entry saved successfully and synced to the ML training dataset.",
        )
        self.assertEqual(training_record.target_condition, "Respiratory")
        self.assertEqual(training_record.target_specialization, "Pulmonology")
        self.assertGreater(training_record.quality_score, 0)

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
        training_record.refresh_from_db()
        self.assertEqual(edit_response.status_code, 200)
        self.assertEqual(treatment_entry.treatment_notes, "Updated follow-up after inhaler review.")
        self.assertEqual(training_record.target_treatment, "Updated follow-up after inhaler review.")

        delete_response = self.client.post(
            reverse("treatment_entry_delete", args=[analysis.id, treatment_entry.id]),
            follow=True,
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(TreatmentEntry.objects.filter(id=treatment_entry.id).exists())
        self.assertFalse(TreatmentTrainingRecord.objects.filter(treatment_id=treatment_entry.id).exists())


class TrainingPipelineTests(TestCase):
    def setUp(self):
        self.user = user_model.objects.create_user(
            username="ml_user",
            email="ml@example.com",
            password="SecurePass123!",
        )

    def _create_reviewed_case(self, title, condition, symptoms_text, report_text, specialization, notes):
        analysis = MedicalAnalysis.objects.create(
            user=self.user,
            title=title,
            symptoms_text=symptoms_text,
            report_text=report_text,
            ai_summary=f"AI review for {condition}",
            predicted_condition=condition,
            risk_level="Medium",
            detected_conditions_count=1,
            model_source="heuristic",
        )
        return TreatmentEntry.objects.create(
            analysis=analysis,
            doctor_name="Dr. Review",
            doctor_id=f"DOC-{analysis.id}",
            specialization=specialization,
            treatment_notes=notes,
            added_by=self.user,
        )

    def test_export_training_dataset_command_writes_jsonl(self):
        self._create_reviewed_case(
            "Respiratory case",
            "Respiratory",
            "Persistent cough and wheeze",
            "Bronchial inflammation noted in report",
            "Pulmonology",
            "Start bronchodilator and follow-up review.",
        )

        output_path = Path("medical_app") / "ml_models" / f"test-training-{uuid.uuid4().hex}.jsonl"
        try:
            call_command("export_training_dataset", output=str(output_path))

            self.assertTrue(output_path.exists())
            self.assertIn("Respiratory", output_path.read_text(encoding="utf-8"))
        finally:
            if output_path.exists():
                output_path.unlink()

    def test_generic_ai_condition_falls_back_to_doctor_specialization(self):
        treatment = self._create_reviewed_case(
            "Eye case",
            "Visual review suggested",
            "",
            "Eye irritation with redness",
            "Eye Specialist",
            "Clean the eye and monitor irritation.",
        )

        training_record = TreatmentTrainingRecord.objects.get(treatment=treatment)

        self.assertEqual(training_record.target_condition, "Eye Specialist")
        self.assertIn("fell back to doctor specialization", training_record.review_notes)

    def test_train_condition_model_creates_model_used_by_analysis_engine(self):
        self._create_reviewed_case(
            "Respiratory case",
            "Respiratory",
            "Persistent cough and wheeze",
            "Bronchial inflammation and asthma concern",
            "Pulmonology",
            "Start bronchodilator and inhaler support.",
        )
        self._create_reviewed_case(
            "Infection case",
            "Infection",
            "Fever with throat pain",
            "Bacterial infection markers elevated",
            "Internal Medicine",
            "Start antibiotic review and hydration plan.",
        )

        model_path = Path("medical_app") / "ml_models" / f"test-report-classifier-{uuid.uuid4().hex}.pkl"
        metrics_path = Path("medical_app") / "ml_models" / f"test-report-metrics-{uuid.uuid4().hex}.json"
        try:
            call_command(
                "train_condition_model",
                output=str(model_path),
                metrics_output=str(metrics_path),
                minimum_records=2,
            )

            self.assertTrue(model_path.exists())
            self.assertTrue(metrics_path.exists())

            metrics = load_evaluation_report(metrics_path)
            self.assertEqual(metrics["total_records"], 2)
            self.assertEqual(metrics["train_count"], 1)
            self.assertEqual(metrics["test_count"], 1)

            with patch("medical_app.analysis_engine.REPORT_MODEL_PATH", model_path):
                result = analyze_report_text("Patient has persistent cough and wheeze with bronchial irritation.")

            self.assertEqual(result["model_source"], "trained-model")
            self.assertEqual(result["predicted_condition"], "Respiratory")
        finally:
            if model_path.exists():
                model_path.unlink()
            if metrics_path.exists():
                metrics_path.unlink()


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
