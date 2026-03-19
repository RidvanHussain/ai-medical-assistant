import uuid

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="profile",
        on_delete=models.CASCADE,
    )
    mobile_number = models.CharField(max_length=20)
    last_known_location = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile: {self.user.username}"

    @property
    def full_name(self):
        return self.user.get_full_name().strip() or self.user.username


class LoginActivity(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="login_activities",
        on_delete=models.CASCADE,
    )
    session_key = models.CharField(max_length=40, db_index=True)
    ip_address = models.CharField(max_length=45, blank=True)
    location_label = models.CharField(max_length=255, blank=True)
    device_name = models.CharField(max_length=255, blank=True)
    browser_name = models.CharField(max_length=100, blank=True)
    user_agent = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "session_key")
        ordering = ("-last_seen",)

    def __str__(self):
        return f"{self.user.username} on {self.device_name or 'Unknown device'}"


class FeaturedImage(models.Model):
    title = models.CharField(max_length=120)
    caption = models.CharField(max_length=255)
    image_url = models.URLField(max_length=500)
    target_url = models.CharField(max_length=255)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("display_order", "title")

    def __str__(self):
        return self.title


class PendingRegistration(models.Model):
    verification_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(max_length=254)
    mobile_number = models.CharField(max_length=20)
    password_hash = models.CharField(max_length=128)
    email_otp_hash = models.CharField(max_length=128, blank=True)
    mobile_otp_hash = models.CharField(max_length=128, blank=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    verification_attempts = models.PositiveIntegerField(default=0)
    last_sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Pending registration for {self.email}"

    @property
    def is_expired(self):
        return not self.expires_at or timezone.now() > self.expires_at

    @property
    def masked_email(self):
        local_part, _, domain = self.email.partition("@")
        if len(local_part) <= 2:
            masked_local = f"{local_part[:1]}*"
        else:
            masked_local = f"{local_part[:2]}{'*' * max(1, len(local_part) - 2)}"
        return f"{masked_local}@{domain}"

    @property
    def masked_mobile_number(self):
        if len(self.mobile_number) <= 4:
            return "*" * len(self.mobile_number)
        return f"{'*' * (len(self.mobile_number) - 4)}{self.mobile_number[-4:]}"

    def matches_email_otp(self, otp_value):
        return bool(self.email_otp_hash and otp_value and check_password(otp_value, self.email_otp_hash))

    def matches_mobile_otp(self, otp_value):
        return bool(self.mobile_otp_hash and otp_value and check_password(otp_value, self.mobile_otp_hash))


class MedicalAnalysis(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="medical_analyses",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=150, blank=True)
    symptoms_text = models.TextField(blank=True)
    transcription_text = models.TextField(blank=True)
    report_text = models.TextField(blank=True)
    report_file = models.FileField(upload_to="medical_reports/", blank=True, null=True)
    previous_report_text = models.TextField(blank=True)
    previous_report_file = models.FileField(upload_to="medical_reports/", blank=True, null=True)
    medical_image = models.FileField(upload_to="analysis_images/", blank=True, null=True)
    ai_summary = models.TextField(blank=True)
    predicted_condition = models.CharField(max_length=120, blank=True)
    detected_conditions_count = models.PositiveIntegerField(default=0)
    risk_level = models.CharField(max_length=32, blank=True)
    confidence_score = models.FloatField(default=0)
    disease_percentage = models.FloatField(blank=True, null=True)
    previous_disease_percentage = models.FloatField(blank=True, null=True)
    percentage_reduced = models.FloatField(blank=True, null=True)
    percentage_remaining = models.FloatField(blank=True, null=True)
    progression_status = models.CharField(max_length=40, blank=True)
    model_source = models.CharField(max_length=40, default="heuristic")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.title or f"Medical Analysis {self.id}"


class TreatmentEntry(models.Model):
    analysis = models.ForeignKey(
        MedicalAnalysis,
        related_name="treatments",
        on_delete=models.CASCADE,
    )
    doctor_name = models.CharField(max_length=150)
    doctor_id = models.CharField(max_length=100)
    specialization = models.CharField(max_length=150)
    contact_details = models.CharField(max_length=150, blank=True)
    treatment_notes = models.TextField()
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="treatment_entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.doctor_name} - {self.analysis_id}"


class TreatmentTrainingRecord(models.Model):
    treatment = models.OneToOneField(
        TreatmentEntry,
        related_name="training_record",
        on_delete=models.CASCADE,
    )
    analysis = models.ForeignKey(
        MedicalAnalysis,
        related_name="training_records",
        on_delete=models.CASCADE,
    )
    source_type = models.CharField(max_length=40, default="doctor_reviewed_case")
    input_text = models.TextField()
    ai_context = models.TextField(blank=True)
    target_condition = models.CharField(max_length=120, blank=True)
    target_specialization = models.CharField(max_length=150, blank=True)
    target_treatment = models.TextField()
    feature_snapshot = models.JSONField(default=dict, blank=True)
    quality_score = models.PositiveSmallIntegerField(default=0)
    is_approved = models.BooleanField(default=True)
    review_notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return f"Training record for treatment {self.treatment_id}"


class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Session {self.id} ({self.user})"


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    session = models.ForeignKey(ChatSession, related_name="messages", on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    text = models.TextField(blank=True)
    attachment = models.FileField(upload_to="chat_files/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.role} @ {self.created_at}"
