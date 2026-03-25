from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_migrate, post_save
from django.dispatch import receiver

from .models import (
    FeaturedImage,
    LoginActivity,
    MedicalAnalysis,
    TreatmentEntry,
    TreatmentTrainingRecord,
    UserProfile,
)
from .selectors.dashboard import bump_dashboard_cache_version, bump_featured_images_cache_version
from .services.bootstrap import bootstrap_defaults
from .training_pipeline import sync_training_record_for_treatment

user_model = get_user_model()


@receiver(post_save, sender=user_model)
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance, mobile_number="")
    else:
        UserProfile.objects.get_or_create(user=instance, defaults={"mobile_number": ""})


@receiver(post_save, sender=TreatmentEntry)
def sync_treatment_training_record(sender, instance, **kwargs):
    sync_training_record_for_treatment(instance)


@receiver(post_migrate)
def ensure_default_records_after_migrate(sender, **kwargs):
    if getattr(sender, "name", "") != "medical_app":
        return
    bootstrap_defaults()


@receiver(post_save, sender=FeaturedImage)
@receiver(post_delete, sender=FeaturedImage)
def invalidate_featured_image_cache(sender, **kwargs):
    bump_featured_images_cache_version()


@receiver(post_save, sender=LoginActivity)
@receiver(post_delete, sender=LoginActivity)
@receiver(post_save, sender=MedicalAnalysis)
@receiver(post_delete, sender=MedicalAnalysis)
@receiver(post_save, sender=TreatmentEntry)
@receiver(post_delete, sender=TreatmentEntry)
@receiver(post_save, sender=TreatmentTrainingRecord)
@receiver(post_delete, sender=TreatmentTrainingRecord)
@receiver(post_save, sender=UserProfile)
@receiver(post_delete, sender=UserProfile)
def invalidate_dashboard_cache(sender, **kwargs):
    bump_dashboard_cache_version()
