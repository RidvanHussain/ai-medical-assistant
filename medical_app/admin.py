from django.contrib import admin

from .models import (
    ChatMessage,
    ChatSession,
    FeaturedImage,
    LoginActivity,
    MedicalAnalysis,
    PendingRegistration,
    TreatmentEntry,
    UserProfile,
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "mobile_number", "last_known_location", "updated_at")
    search_fields = ("user__username", "user__email", "mobile_number")
    ordering = ("user__username",)


@admin.register(LoginActivity)
class LoginActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "device_name", "browser_name", "location_label", "is_active", "last_seen")
    list_filter = ("is_active", "browser_name", "created_at")
    search_fields = ("user__username", "user__email", "device_name", "location_label")
    ordering = ("-last_seen",)


@admin.register(FeaturedImage)
class FeaturedImageAdmin(admin.ModelAdmin):
    list_display = ("title", "target_url", "display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "caption", "target_url")
    ordering = ("display_order", "title")


@admin.register(PendingRegistration)
class PendingRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "mobile_number",
        "verification_attempts",
        "expires_at",
        "last_sent_at",
        "created_at",
    )
    search_fields = ("email", "mobile_number", "first_name", "last_name")
    ordering = ("-created_at",)


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at", "message_count")
    list_filter = ("created_at",)
    search_fields = ("user__username", "user__email")
    ordering = ("-created_at",)

    @staticmethod
    def message_count(obj):
        return obj.messages.count()


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "created_at", "has_attachment")
    list_filter = ("role", "created_at")
    search_fields = ("text", "session__user__username", "session__user__email")
    ordering = ("-created_at",)

    @staticmethod
    def has_attachment(obj):
        return bool(obj.attachment)


@admin.register(MedicalAnalysis)
class MedicalAnalysisAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "user",
        "predicted_condition",
        "risk_level",
        "progression_status",
        "model_source",
        "created_at",
    )
    list_filter = ("risk_level", "progression_status", "model_source", "created_at")
    search_fields = (
        "title",
        "predicted_condition",
        "user__username",
        "user__email",
        "symptoms_text",
        "report_text",
    )
    ordering = ("-created_at",)


@admin.register(TreatmentEntry)
class TreatmentEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "analysis",
        "doctor_name",
        "doctor_id",
        "specialization",
        "added_by",
        "created_at",
    )
    list_filter = ("specialization", "created_at", "updated_at")
    search_fields = (
        "doctor_name",
        "doctor_id",
        "specialization",
        "treatment_notes",
        "analysis__title",
    )
    ordering = ("-created_at",)
