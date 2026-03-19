from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import TreatmentEntry, UserProfile
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
