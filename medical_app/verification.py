import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.utils import timezone
import httpx


logger = logging.getLogger(__name__)


def generate_otp_code():
    return f"{secrets.randbelow(1000000):06d}"


def _build_email_message(first_name, code):
    return "\n".join(
        [
            f"Hello {first_name},",
            "",
            "Use the following OTP to verify your AI Medical Assistant registration email address:",
            f"Email OTP: {code}",
            "",
            f"This code will expire in {settings.REGISTRATION_OTP_EXPIRY_MINUTES} minutes.",
            "If you did not request this, you can ignore this message.",
        ]
    )


def _build_mobile_message(first_name, code):
    return (
        f"AI Medical Assistant OTP for {first_name}: {code}. "
        f"Valid for {settings.REGISTRATION_OTP_EXPIRY_MINUTES} minutes."
    )


def send_email_otp(recipient_email, first_name, code):
    send_mail(
        subject="Verify your AI Medical Assistant email",
        message=_build_email_message(first_name, code),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient_email],
        fail_silently=False,
    )


def send_mobile_otp(mobile_number, first_name, code):
    sms_message = _build_mobile_message(first_name, code)

    if settings.SMS_BACKEND == "console":
        logger.warning("SMS OTP to %s: %s", mobile_number, sms_message)
        return

    if settings.SMS_BACKEND == "twilio":
        if not (
            settings.TWILIO_ACCOUNT_SID
            and settings.TWILIO_AUTH_TOKEN
            and settings.TWILIO_FROM_NUMBER
        ):
            raise RuntimeError("Twilio SMS settings are incomplete.")

        response = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json",
            data={
                "To": mobile_number,
                "From": settings.TWILIO_FROM_NUMBER,
                "Body": sms_message,
            },
            auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            timeout=15,
        )
        response.raise_for_status()
        return

    raise RuntimeError(f"Unsupported SMS backend: {settings.SMS_BACKEND}")


def issue_registration_otp_challenge(pending_registration):
    email_code = generate_otp_code()
    mobile_code = generate_otp_code()
    pending_registration.email_otp_hash = make_password(email_code)
    pending_registration.mobile_otp_hash = make_password(mobile_code)
    pending_registration.expires_at = timezone.now() + timedelta(
        minutes=settings.REGISTRATION_OTP_EXPIRY_MINUTES
    )
    pending_registration.verification_attempts = 0
    pending_registration.last_sent_at = timezone.now()
    pending_registration.save(
        update_fields=[
            "email_otp_hash",
            "mobile_otp_hash",
            "expires_at",
            "verification_attempts",
            "last_sent_at",
            "updated_at",
        ]
    )

    send_email_otp(pending_registration.email, pending_registration.first_name, email_code)
    send_mobile_otp(pending_registration.mobile_number, pending_registration.first_name, mobile_code)
