import csv
import json
import uuid
import zipfile
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .analysis_engine import analyze_report_text
from .dataset_importer import load_classifier_records, load_qa_corpus_entries
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


class FakePredictionModel:
    def __init__(self, prediction):
        self.prediction = prediction

    def predict(self, texts):
        return [self.prediction for _ in texts]


def write_csv_dataset(csv_path, fieldnames, rows):
    with csv_path.open("w", encoding="utf-8", newline="") as dataset_file:
        writer = csv.DictWriter(dataset_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_zipped_csv(zip_path, member_name, fieldnames, rows):
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with archive.open(member_name, "w") as archive_file:
            text_stream = StringIO()
            writer = csv.DictWriter(text_stream, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
            archive_file.write(text_stream.getvalue().encode("utf-8"))


class PublicPageTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_homepage_loads_featured_images(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quick Access")
        self.assertContains(response, "Important Notice")
        self.assertTrue(FeaturedImage.objects.exists())
        self.assertContains(response, "medical-assistant-logo.svg")

    def test_homepage_moves_report_tools_into_collapsible_panel(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open Reports &amp; Comparison")
        self.assertContains(response, reverse("report_intake"))
        self.assertNotContains(response, "report-tools-panel")
        self.assertContains(response, "upload.js")

    def test_report_workspace_page_loads_report_fields(self):
        response = self.client.get(reverse("report_intake"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current Medical Report")
        self.assertContains(response, "Previous Report Comparison")
        self.assertContains(response, "Analyze Reports")

    def test_healthcheck_endpoint_returns_ok(self):
        response = self.client.get(reverse("healthcheck"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


class LoginPageTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_login_page_shows_disabled_gmail_button_when_oauth_not_configured(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login with Gmail")
        self.assertContains(response, "GOOGLE_OAUTH_CLIENT_ID")
        self.assertContains(response, "disabled")

    @override_settings(
        GOOGLE_OAUTH_CLIENT_ID="google-client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="google-client-secret",
    )
    def test_login_page_shows_active_gmail_button_when_oauth_configured(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Login with Gmail")
        self.assertContains(response, "/accounts/google/login/")
        self.assertNotContains(response, "Configure <code>GOOGLE_OAUTH_CLIENT_ID</code>")


class AnalysisEngineTests(TestCase):
    @patch("medical_app.analysis_engine._load_pickle_model")
    def test_report_analysis_prefers_heuristics_when_trained_model_disagrees(self, mock_model_loader):
        mock_model_loader.return_value = FakePredictionModel("Bronchitis")

        result = analyze_report_text(
            "Persistent cough with mild fever for three days. Inflammation markers are elevated."
        )

        self.assertEqual(result["predicted_condition"], "Infection")
        self.assertEqual(result["model_source"], "heuristic")

    @patch("medical_app.analysis_engine._load_pickle_model")
    def test_report_analysis_uses_trained_model_when_prediction_matches_supported_label(
        self,
        mock_model_loader,
    ):
        mock_model_loader.return_value = FakePredictionModel("Respiratory")

        result = analyze_report_text(
            "Patient has persistent cough and wheeze with bronchial irritation."
        )

        self.assertEqual(result["predicted_condition"], "Respiratory")
        self.assertEqual(result["model_source"], "trained-model")


class DatasetImportTests(TestCase):
    def test_load_classifier_records_reads_zip_files_and_excludes_noisy_sources_by_default(self):
        with TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir)
            write_csv_dataset(
                dataset_dir / "medical_data.csv",
                ["Patient_Problem", "Disease", "Prescription"],
                [
                    {
                        "Patient_Problem": "Recurring wheeze and chest tightness",
                        "Disease": "Asthma",
                        "Prescription": "Inhaler support",
                    }
                ],
            )
            write_zipped_csv(
                dataset_dir / "Diseases_Symptoms.csv.zip",
                "Diseases_Symptoms.csv",
                ["Name", "Symptoms", "Treatments", "Disease_Code", "Contagious", "Chronic"],
                [
                    {
                        "Name": "Eczema",
                        "Symptoms": "itchy skin and rash",
                        "Treatments": "moisturizers",
                        "Disease_Code": "D1",
                        "Contagious": "False",
                        "Chronic": "True",
                    }
                ],
            )
            write_zipped_csv(
                dataset_dir / "medical_question_answer_dataset_50000.csv.zip",
                "medical_question_answer_dataset_50000.csv",
                ["ID", "Symptoms/Question", "Disease Prediction", "Recommended Medicines", "Advice"],
                [
                    {
                        "ID": "1",
                        "Symptoms/Question": "persistent cough with mucus",
                        "Disease Prediction": "Bronchitis",
                        "Recommended Medicines": "Azithromycin",
                        "Advice": "Drink fluids",
                    },
                    {
                        "ID": "2",
                        "Symptoms/Question": "persistent cough with mucus",
                        "Disease Prediction": "Bronchitis",
                        "Recommended Medicines": "Azithromycin",
                        "Advice": "Drink fluids",
                    },
                ],
            )
            write_zipped_csv(
                dataset_dir / "train.csv.zip",
                "train.csv",
                ["qtype", "Question", "Answer"],
                [
                    {
                        "qtype": "symptoms",
                        "Question": "What are the symptoms of malaria?",
                        "Answer": "Fever and chills.",
                    }
                ],
            )

            records, summary = load_classifier_records(
                dataset_dir,
                dedupe=True,
                minimum_occurrences=1,
            )

            self.assertEqual(len(records), 3)
            self.assertEqual(summary["duplicates_removed"], 1)
            self.assertFalse(any(record["source"] == "train.csv" for record in records))
            self.assertTrue(summary["datasets"]["medical_data.csv"]["found"])
            self.assertTrue(summary["datasets"]["Diseases_Symptoms.csv"]["found"])
            self.assertTrue(summary["datasets"]["medical_question_answer_dataset_50000.csv"]["found"])

    def test_load_qa_corpus_entries_deduplicates_exact_duplicate_pairs(self):
        with TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir)
            write_csv_dataset(
                dataset_dir / "medical_data.csv",
                ["Patient_Problem", "Disease", "Prescription"],
                [
                    {
                        "Patient_Problem": "Constant fatigue and muscle weakness",
                        "Disease": "Chronic Fatigue Syndrome",
                        "Prescription": "graded exercise",
                    }
                ],
            )
            write_csv_dataset(
                dataset_dir / "Diseases_Symptoms.csv",
                ["Name", "Symptoms", "Treatments", "Disease_Code", "Contagious", "Chronic"],
                [
                    {
                        "Name": "Migraine",
                        "Symptoms": "head pain with light sensitivity",
                        "Treatments": "rest in a dark room",
                        "Disease_Code": "D2",
                        "Contagious": "False",
                        "Chronic": "True",
                    }
                ],
            )
            write_csv_dataset(
                dataset_dir / "medical_question_answer_dataset_50000.csv",
                ["ID", "Symptoms/Question", "Disease Prediction", "Recommended Medicines", "Advice"],
                [
                    {
                        "ID": "1",
                        "Symptoms/Question": "muscle cramps and weakness",
                        "Disease Prediction": "Electrolyte Imbalance",
                        "Recommended Medicines": "Electrolyte solution",
                        "Advice": "Stay hydrated",
                    },
                    {
                        "ID": "2",
                        "Symptoms/Question": "muscle cramps and weakness",
                        "Disease Prediction": "Electrolyte Imbalance",
                        "Recommended Medicines": "Electrolyte solution",
                        "Advice": "Stay hydrated",
                    },
                ],
            )

            entries, summary = load_qa_corpus_entries(dataset_dir, dedupe=True)

            self.assertEqual(len(entries), 3)
            self.assertEqual(summary["duplicates_removed"], 1)
            self.assertEqual(summary["source_distribution"]["medical_question_answer_dataset_50000.csv"], 1)

    def test_import_external_datasets_dry_run_reports_clean_records(self):
        with TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir)
            write_csv_dataset(
                dataset_dir / "medical_data.csv",
                ["Patient_Problem", "Disease", "Prescription"],
                [
                    {
                        "Patient_Problem": "Recurring wheeze and chest tightness",
                        "Disease": "Asthma",
                        "Prescription": "Inhaler support",
                    }
                ],
            )
            write_csv_dataset(
                dataset_dir / "Diseases_Symptoms.csv",
                ["Name", "Symptoms", "Treatments", "Disease_Code", "Contagious", "Chronic"],
                [
                    {
                        "Name": "Eczema",
                        "Symptoms": "itchy skin and rash",
                        "Treatments": "moisturizers",
                        "Disease_Code": "D1",
                        "Contagious": "False",
                        "Chronic": "True",
                    }
                ],
            )
            write_csv_dataset(
                dataset_dir / "medical_question_answer_dataset_50000.csv",
                ["ID", "Symptoms/Question", "Disease Prediction", "Recommended Medicines", "Advice"],
                [
                    {
                        "ID": "1",
                        "Symptoms/Question": "persistent cough with mucus",
                        "Disease Prediction": "Bronchitis",
                        "Recommended Medicines": "Azithromycin",
                        "Advice": "Drink fluids",
                    },
                    {
                        "ID": "2",
                        "Symptoms/Question": "persistent cough with mucus",
                        "Disease Prediction": "Bronchitis",
                        "Recommended Medicines": "Azithromycin",
                        "Advice": "Drink fluids",
                    },
                ],
            )

            output = StringIO()
            call_command(
                "import_external_datasets",
                datasets_dir=str(dataset_dir),
                dry_run=True,
                dedupe=True,
                minimum_condition_occurrences=1,
                stdout=output,
            )

            self.assertIn("Would create 3 external training records", output.getvalue())


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
        cache.clear()
        self.user = user_model.objects.create_user(
            username="clinician",
            email="clinician@example.com",
            password="SecurePass123!",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={
                "mobile_number": "9999999999",
                "language_preference": "hindi",
                "response_style": "clinical",
                "ai_risk_preference": "conservative",
            },
        )

    def test_chat_requires_login(self):
        response = self.client.get(reverse("chat"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    @patch(
        "medical_app.views.answer_question",
        return_value={
            "answer": "Possible condition: Bronchitis. Recommended medicines: Azithromycin.",
            "score": 0.71,
            "source_metadata": {
                "source": "medical_question_answer_dataset_50000.csv",
                "condition": "Bronchitis",
            },
            "used_local_qa": True,
        },
    )
    @patch("medical_app.views.analyze_image_with_query")
    def test_chat_uses_local_qa_answer_for_high_confidence_text_queries(self, mock_ai, mock_local_qa):
        self.client.login(username="clinician", password="SecurePass123!")

        response = self.client.post(
            reverse("chat"),
            {"message": "persistent cough with mucus"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Possible condition: Bronchitis")
        self.assertContains(response, "Source: medical_question_answer_dataset_50000.csv (Bronchitis)")
        mock_ai.assert_not_called()

    @patch("medical_app.views.answer_question", return_value={"used_local_qa": False})
    @patch("medical_app.views.analyze_image_with_query", return_value="Structured reply.")
    def test_chat_escapes_rendered_message_content(self, mock_ai, mock_local_qa):
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

    def test_chat_page_loads_page_specific_script(self):
        self.client.login(username="clinician", password="SecurePass123!")

        response = self.client.get(reverse("chat"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chat.js")

    @patch("medical_app.views.answer_question", return_value={"used_local_qa": False})
    @patch("medical_app.views.analyze_image_with_query", return_value="Structured reply.")
    def test_chat_prompt_uses_saved_profile_preferences(self, mock_ai, mock_local_qa):
        self.client.login(username="clinician", password="SecurePass123!")

        self.client.post(
            reverse("chat"),
            {"message": "I have chest tightness today"},
            follow=True,
        )

        prompt = mock_ai.call_args.kwargs["query"]
        self.assertIn("Respond in hindi.", prompt)
        self.assertIn("Escalate uncertainty carefully", prompt)
        self.assertIn("clinical tone", prompt)


class DashboardTests(TestCase):
    def setUp(self):
        cache.clear()
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

    def test_dashboard_page_loads_page_specific_script(self):
        self.client.login(username="admin_user", password="SecurePass123!")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dashboard.js")
        self.assertContains(response, "Quick Actions")
        self.assertContains(response, "AI Insights")
        self.assertContains(response, "Analytics")


class HistoryWorkspaceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = user_model.objects.create_user(
            username="history_user",
            email="history@example.com",
            password="SecurePass123!",
        )
        UserProfile.objects.update_or_create(
            user=self.user,
            defaults={"mobile_number": "7777777777"},
        )
        self.analysis = MedicalAnalysis.objects.create(
            user=self.user,
            title="Timeline Case",
            symptoms_text="Dry cough, chest heaviness, and mild fever",
            report_text="Inflammation markers are moderately elevated.",
            ai_summary="Possible respiratory inflammation with follow-up required.",
            predicted_condition="Respiratory",
            risk_level="Medium",
            progression_status="Improved",
            disease_percentage=35,
        )
        TreatmentEntry.objects.create(
            analysis=self.analysis,
            doctor_name="Dr. Lane",
            doctor_id="DOC-301",
            specialization="Pulmonology",
            treatment_notes="Continue inhaler support and monitor oxygen saturation.",
            added_by=self.user,
        )
        from .models import ChatSession

        self.session = ChatSession.objects.create(user=self.user)
        ChatMessage.objects.create(session=self.session, role="user", text="Can I continue work?")
        ChatMessage.objects.create(session=self.session, role="assistant", text="Take rest and monitor symptoms.")

    def test_history_page_shows_timeline_filters_and_detail_panel(self):
        self.client.login(username="history_user", password="SecurePass123!")

        response = self.client.get(reverse("history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filter + Search")
        self.assertContains(response, "Timeline")
        self.assertContains(response, "Timeline Case")
        self.assertContains(response, "Detailed View")
        self.assertContains(response, "View Record")


class ClinicalAnalysisTests(TestCase):
    def setUp(self):
        cache.clear()
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

    def test_index_page_loads_upload_script(self):
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "upload.js")

    @patch("medical_app.views.text_to_speech_with_edge")
    @patch("medical_app.views.analyze_image_with_query", return_value="Structured report summary.")
    def test_report_workspace_can_compare_reports(self, mock_ai, mock_tts):
        self.client.login(username="doctor_user", password="SecurePass123!")

        response = self.client.post(
            reverse("report_intake"),
            {
                "report_notes": "Current report shows disease burden at 25% with improved response.",
                "previous_report_notes": "Previous report recorded disease burden at 70%.",
                "language": "english",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Disease Burden Comparison")
        self.assertContains(response, "Structured report summary.")
        mock_tts.assert_called_once()

    @patch("medical_app.views.text_to_speech_with_edge")
    @patch("medical_app.views.analyze_image_with_query", return_value="Structured clinical summary.")
    def test_index_skips_voice_generation_when_user_disables_voice_summary(self, mock_ai, mock_tts):
        self.user.profile.voice_summary_enabled = False
        self.user.profile.save(update_fields=["voice_summary_enabled"])
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

        self.assertEqual(response.status_code, 200)
        mock_tts.assert_not_called()

    def test_analysis_detail_requires_login(self):
        analysis = MedicalAnalysis.objects.create(
            user=self.user,
            title="Test Analysis",
            predicted_condition="General review required",
        )

        response = self.client.get(reverse("analysis_detail", args=[analysis.id]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_analysis_detail_renders_uploaded_file_links(self):
        self.client.login(username="doctor_user", password="SecurePass123!")
        analysis = MedicalAnalysis.objects.create(
            user=self.user,
            title="Stored Files Analysis",
            predicted_condition="Respiratory",
            risk_level="Medium",
            report_file="medical_reports/test-report.txt",
            previous_report_file="medical_reports/test-previous.txt",
            medical_image="analysis_images/test-image.jpg",
        )

        response = self.client.get(reverse("analysis_detail", args=[analysis.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/media/medical_reports/test-report.txt")
        self.assertContains(response, "/media/medical_reports/test-previous.txt")
        self.assertContains(response, "/media/analysis_images/test-image.jpg")

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
        cache.clear()
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

    def _create_condition_series(self, condition, specialization, symptom_prefix, report_prefix, note_prefix, count):
        for index in range(count):
            self._create_reviewed_case(
                f"{condition} case {index}",
                condition,
                f"{symptom_prefix} {index}",
                f"{report_prefix} {index}",
                specialization,
                f"{note_prefix} {index}",
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
        self._create_condition_series(
            "Respiratory",
            "Pulmonology",
            "Persistent cough and wheeze",
            "Bronchial inflammation and asthma concern",
            "Start bronchodilator and inhaler support.",
            3,
        )
        self._create_condition_series(
            "Infection",
            "Internal Medicine",
            "Fever with throat pain",
            "Bacterial infection markers elevated",
            "Start antibiotic review and hydration plan.",
            3,
        )

        model_path = Path("medical_app") / "ml_models" / f"test-report-classifier-{uuid.uuid4().hex}.pkl"
        metrics_path = Path("medical_app") / "ml_models" / f"test-report-metrics-{uuid.uuid4().hex}.json"
        summary_path = Path("medical_app") / "ml_models" / f"test-report-summary-{uuid.uuid4().hex}.json"
        try:
            call_command(
                "train_condition_model",
                output=str(model_path),
                metrics_output=str(metrics_path),
                summary_output=str(summary_path),
                minimum_records=6,
            )

            self.assertTrue(model_path.exists())
            self.assertTrue(metrics_path.exists())
            self.assertTrue(summary_path.exists())

            metrics = load_evaluation_report(metrics_path)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(metrics["total_records"], 6)
            self.assertEqual(metrics["train_count"], 4)
            self.assertEqual(metrics["test_count"], 2)
            self.assertIn("macro_f1", metrics)
            self.assertEqual(summary["filtered_record_count"], 6)
            self.assertEqual(summary["duplicates_removed"], 0)

            with patch("medical_app.analysis_engine.REPORT_MODEL_PATH", model_path):
                result = analyze_report_text("Patient has persistent cough and wheeze with bronchial irritation.")

            self.assertEqual(result["model_source"], "trained-model")
            self.assertEqual(result["predicted_condition"], "Respiratory")
        finally:
            if model_path.exists():
                model_path.unlink()
            if metrics_path.exists():
                metrics_path.unlink()
            if summary_path.exists():
                summary_path.unlink()

    def test_train_qa_ranker_command_writes_runtime_artifacts(self):
        with TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir)
            write_csv_dataset(
                dataset_dir / "medical_data.csv",
                ["Patient_Problem", "Disease", "Prescription"],
                [
                    {
                        "Patient_Problem": "Constant fatigue and muscle weakness",
                        "Disease": "Chronic Fatigue Syndrome",
                        "Prescription": "graded exercise",
                    }
                ],
            )
            write_csv_dataset(
                dataset_dir / "Diseases_Symptoms.csv",
                ["Name", "Symptoms", "Treatments", "Disease_Code", "Contagious", "Chronic"],
                [
                    {
                        "Name": "Migraine",
                        "Symptoms": "head pain with light sensitivity",
                        "Treatments": "rest in a dark room",
                        "Disease_Code": "D2",
                        "Contagious": "False",
                        "Chronic": "True",
                    }
                ],
            )
            write_csv_dataset(
                dataset_dir / "medical_question_answer_dataset_50000.csv",
                ["ID", "Symptoms/Question", "Disease Prediction", "Recommended Medicines", "Advice"],
                [
                    {
                        "ID": "1",
                        "Symptoms/Question": "muscle cramps and weakness",
                        "Disease Prediction": "Electrolyte Imbalance",
                        "Recommended Medicines": "Electrolyte solution",
                        "Advice": "Stay hydrated",
                    },
                    {
                        "ID": "2",
                        "Symptoms/Question": "severe headache with light sensitivity",
                        "Disease Prediction": "Migraine",
                        "Recommended Medicines": "Pain relievers",
                        "Advice": "Rest in a quiet room",
                    },
                ],
            )

            qa_model_path = Path("medical_app") / "ml_models" / f"test-qa-ranker-{uuid.uuid4().hex}.pkl"
            qa_corpus_path = Path("medical_app") / "ml_models" / f"test-qa-corpus-{uuid.uuid4().hex}.jsonl"
            qa_metrics_path = Path("medical_app") / "ml_models" / f"test-qa-metrics-{uuid.uuid4().hex}.json"
            qa_summary_path = Path("medical_app") / "ml_models" / f"test-qa-summary-{uuid.uuid4().hex}.json"

            try:
                call_command(
                    "train_qa_ranker",
                    datasets_dir=str(dataset_dir),
                    dedupe=True,
                    output=str(qa_model_path),
                    corpus_output=str(qa_corpus_path),
                    metrics_output=str(qa_metrics_path),
                    summary_output=str(qa_summary_path),
                )

                self.assertTrue(qa_model_path.exists())
                self.assertTrue(qa_corpus_path.exists())
                self.assertTrue(qa_metrics_path.exists())
                self.assertTrue(qa_summary_path.exists())

                qa_metrics = json.loads(qa_metrics_path.read_text(encoding="utf-8"))
                qa_summary = json.loads(qa_summary_path.read_text(encoding="utf-8"))
                self.assertEqual(qa_metrics["corpus_count"], 4)
                self.assertIn("hit_rate_at_1", qa_metrics)
                self.assertEqual(qa_summary["total_entries_after_dedupe"], 4)
            finally:
                for artifact_path in (qa_model_path, qa_corpus_path, qa_metrics_path, qa_summary_path):
                    if artifact_path.exists():
                        artifact_path.unlink()


class BootstrapDefaultsCommandTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_bootstrap_defaults_command_is_idempotent(self):
        FeaturedImage.objects.all().delete()
        user_model.objects.filter(username="Admin").delete()

        call_command("bootstrap_defaults")
        call_command("bootstrap_defaults")

        self.assertEqual(FeaturedImage.objects.count(), 3)
        self.assertTrue(user_model.objects.filter(username="Admin").exists())


class MiddlewarePerformanceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = user_model.objects.create_user(
            username="perf_user",
            email="perf@example.com",
            password="SecurePass123!",
        )

    def test_repeat_authenticated_requests_do_not_rewrite_login_activity_immediately(self):
        self.client.login(username="perf_user", password="SecurePass123!")

        first_response = self.client.get(reverse("dashboard"))
        self.assertEqual(first_response.status_code, 200)

        activity = LoginActivity.objects.get(user=self.user)
        first_seen = activity.last_seen
        profile_updated_at = self.user.profile.updated_at

        second_response = self.client.get(reverse("dashboard"))
        self.assertEqual(second_response.status_code, 200)

        activity.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(LoginActivity.objects.filter(user=self.user).count(), 1)
        self.assertEqual(activity.last_seen, first_seen)
        self.assertEqual(self.user.profile.updated_at, profile_updated_at)


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
        self.assertContains(response, "AI Preferences")

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

    def test_user_can_update_medical_and_preference_fields(self):
        self.client.login(username="patient_user", password="SecurePass123!")

        response = self.client.post(
            reverse("change_credentials"),
            {
                "form_type": "profile",
                "profile-first_name": "Patient",
                "profile-last_name": "User",
                "profile-email": "patient@example.com",
                "profile-mobile_number": "8888888888",
                "profile-date_of_birth": "1998-02-10",
                "profile-gender": "female",
                "profile-blood_group": "O+",
                "profile-allergies": "Dust",
                "profile-chronic_conditions": "Asthma",
                "profile-current_medications": "Inhaler",
                "profile-emergency_contact": "Sam 9999999999",
                "profile-language_preference": "hindi",
                "profile-response_style": "clinical",
                "profile-ai_risk_preference": "conservative",
                "profile-notification_preference": "analysis_updates",
                "profile-privacy_mode": "private",
                "profile-performance_mode": "quality",
                "profile-voice_summary_enabled": "on",
                "profile-auto_compare_reports": "on",
            },
            follow=True,
        )

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(self.user.profile.date_of_birth), "1998-02-10")
        self.assertEqual(self.user.profile.blood_group, "O+")
        self.assertEqual(self.user.profile.language_preference, "hindi")
        self.assertEqual(self.user.profile.response_style, "clinical")
        self.assertEqual(self.user.profile.ai_risk_preference, "conservative")
        self.assertEqual(self.user.profile.privacy_mode, "private")

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
