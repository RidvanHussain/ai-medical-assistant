import os
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from dotenv import load_dotenv

from medical_app.ai.brain_of_the_doctor import analyze_image_with_query, encode_image
from medical_app.ai.voice_of_the_doctor import text_to_speech_with_edge
from medical_app.ai.voice_of_the_patient import transcribe_with_groq

from .bootstrap import ensure_demo_setup
from .forms import (
    AdminUserManagementForm,
    ChatForm,
    LoginForm,
    ProfileSettingsForm,
    RegisterForm,
)
from .models import ChatMessage, ChatSession, FeaturedImage, LoginActivity, UserProfile

load_dotenv()

MEDICAL_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
user_model = get_user_model()
staff_required = user_passes_test(lambda user: user.is_staff, login_url="login")


def _save_uploaded_file(uploaded_file, subdirectory, filename):
    target_dir = Path(settings.MEDIA_ROOT) / subdirectory
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / filename

    with file_path.open("wb+") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    return file_path


def _build_media_url(file_path):
    relative_path = Path(file_path).relative_to(settings.MEDIA_ROOT).as_posix()
    return f"{settings.MEDIA_URL}{relative_path}"


def _build_summary_prompt(patient_text, language):
    return "\n".join(
        [
            "You are a professional medical assistant.",
            "Give general educational guidance only and encourage urgent care for emergency symptoms.",
            f"Respond in {language}.",
            "Use this response format:",
            "1) Short introduction paragraph.",
            "2) 3-5 bullet points.",
            "3) Short conclusion with practical next steps.",
            "Keep the answer concise, calm, and easy to understand.",
            f"Patient details: {patient_text or 'No text symptoms provided.'}",
        ]
    )


def _build_chat_prompt(patient_text):
    return "\n".join(
        [
            "You are a professional medical assistant.",
            "Give general educational guidance only and encourage urgent care for emergency symptoms.",
            "Use this response format:",
            "1) Short introduction paragraph.",
            "2) 3-5 bullet points.",
            "3) Short conclusion with practical next steps.",
            "Keep the answer concise and clinically calm.",
            f"Patient question: {patient_text}",
        ]
    )


def _serialize_history(messages_queryset):
    history = []

    for message in messages_queryset:
        history.append(
            {
                "role": message.role,
                "text": message.text,
                "attachment_url": message.attachment.url if message.attachment else "",
                "timestamp": timezone.localtime(message.created_at).strftime("%b %d, %H:%M"),
            }
        )

    return history


def _get_session_for_request(request):
    session = ChatSession.objects.filter(user=request.user).order_by("-created_at").first()
    if not session:
        session = ChatSession.objects.create(user=request.user)
    return session


def _mark_current_login_inactive(request):
    session_key = request.session.session_key
    if not session_key or not request.user.is_authenticated:
        return

    LoginActivity.objects.filter(user=request.user, session_key=session_key).update(is_active=False)


def _get_user_locations(user):
    active_logins = user.login_activities.filter(is_active=True)
    locations = sorted({activity.location_label for activity in active_logins if activity.location_label})
    return locations or ["No active location recorded"]


def _build_login_chart_data():
    points = []
    raw_counts = []

    for days_ago in range(6, -1, -1):
        current_day = timezone.localdate() - timedelta(days=days_ago)
        count = LoginActivity.objects.filter(created_at__date=current_day).count()
        raw_counts.append(count)
        points.append(
            {
                "label": current_day.strftime("%a"),
                "count": count,
            }
        )

    max_count = max(raw_counts) if raw_counts else 1
    max_count = max_count or 1

    for point in points:
        point["height"] = 34 if point["count"] == 0 else 40 + int((point["count"] / max_count) * 110)

    return points


def _build_role_chart_data():
    admin_count = user_model.objects.filter(is_staff=True).count()
    member_count = user_model.objects.filter(is_staff=False).count()
    max_count = max(admin_count, member_count, 1)

    return [
        {
            "label": "Administrators",
            "count": admin_count,
            "width": max(12, int((admin_count / max_count) * 100)) if admin_count else 12,
        },
        {
            "label": "Members",
            "count": member_count,
            "width": max(12, int((member_count / max_count) * 100)) if member_count else 12,
        },
    ]


def _build_user_rows():
    rows = []

    for user in user_model.objects.all().order_by("first_name", "last_name", "email", "username"):
        active_logins = list(user.login_activities.filter(is_active=True))
        rows.append(
            {
                "id": user.id,
                "display_name": user.get_full_name().strip() or user.username,
                "user_id": user.email or user.username,
                "role": "Admin" if user.is_staff else "Member",
                "status": "Online" if active_logins else "Offline",
                "device_count": len(active_logins),
                "locations": _get_user_locations(user),
                "view_url": reverse("dashboard_user_view", args=[user.id]),
                "edit_url": reverse("dashboard_user_edit", args=[user.id]),
                "delete_url": reverse("dashboard_user_delete", args=[user.id]),
            }
        )

    return rows


def _get_mobile_number(user):
    profile = UserProfile.objects.filter(user=user).first()
    return profile.mobile_number if profile and profile.mobile_number else "Not provided"


def index(request):
    ensure_demo_setup()

    speech_text = ""
    doctor_response = ""
    audio_url = ""
    error_message = ""
    submitted_symptoms = ""
    featured_images = FeaturedImage.objects.filter(is_active=True)

    if request.method == "POST":
        image = request.FILES.get("image")
        audio = request.FILES.get("audio")
        submitted_symptoms = (request.POST.get("symptoms") or "").strip()
        language = (request.POST.get("language") or "english").strip().lower()

        if submitted_symptoms:
            speech_text = submitted_symptoms

        encoded_image = None
        mime_type = "image/jpeg"

        try:
            if audio:
                audio_suffix = Path(audio.name).suffix.lower() or ".webm"
                audio_filename = f"{uuid.uuid4()}{audio_suffix}"
                audio_path = _save_uploaded_file(audio, "audio_inputs", audio_filename)
                speech_text = transcribe_with_groq(
                    stt_model="whisper-large-v3",
                    audio_filepath=str(audio_path),
                    GROQ_API_KEY=os.environ.get("GROQ_API_KEY"),
                )

            if image:
                image_suffix = Path(image.name).suffix.lower() or ".jpg"
                image_filename = f"{uuid.uuid4()}{image_suffix}"
                image_path = _save_uploaded_file(image, "clinical_images", image_filename)
                encoded_image, mime_type = encode_image(image_path)

            if speech_text or encoded_image:
                doctor_response = analyze_image_with_query(
                    query=_build_summary_prompt(speech_text, language),
                    encoded_image=encoded_image,
                    model=MEDICAL_MODEL,
                    mime_type=mime_type,
                )

                try:
                    audio_filename = f"{uuid.uuid4()}_response.mp3"
                    generated_audio_path = Path(settings.MEDIA_ROOT) / "generated_audio" / audio_filename
                    generated_audio_path.parent.mkdir(parents=True, exist_ok=True)

                    text_to_speech_with_edge(
                        input_text=doctor_response,
                        output_filepath=str(generated_audio_path),
                        language=language,
                    )
                    audio_url = _build_media_url(generated_audio_path)
                except Exception:
                    error_message = (
                        "The written response is ready, but voice playback could not be generated right now."
                    )
            else:
                error_message = "Provide symptoms, a voice recording, or an image before running analysis."
        except Exception:
            doctor_response = ""
            audio_url = ""
            error_message = (
                "We could not complete the analysis right now. Please verify your AI service "
                "configuration and try again."
            )

    return render(
        request,
        "index.html",
        {
            "speech_text": speech_text,
            "doctor_response": doctor_response,
            "audio_url": audio_url,
            "error_message": error_message,
            "submitted_symptoms": submitted_symptoms,
            "featured_images": featured_images,
        },
    )


@login_required
def dashboard_view(request):
    ensure_demo_setup()

    current_user_logins = request.user.login_activities.filter(is_active=True)
    dashboard_stats = [
        {
            "label": "Registered users",
            "value": user_model.objects.count(),
            "helper": "Total members stored in the platform",
        },
        {
            "label": "Active devices",
            "value": LoginActivity.objects.filter(is_active=True).count(),
            "helper": "Currently signed-in sessions across users",
        },
        {
            "label": "Chat sessions",
            "value": ChatSession.objects.count(),
            "helper": "Conversations created in the assistant",
        },
        {
            "label": "Messages",
            "value": ChatMessage.objects.count(),
            "helper": "Total chat messages saved in history",
        },
    ]

    current_user_summary = {
        "display_name": request.user.get_full_name().strip() or request.user.username,
        "user_id": request.user.email or request.user.username,
        "mobile_number": _get_mobile_number(request.user),
        "role": "Admin" if request.user.is_staff else "Member",
        "device_count": current_user_logins.count(),
        "locations": _get_user_locations(request.user),
    }

    context = {
        "dashboard_stats": dashboard_stats,
        "current_user_summary": current_user_summary,
        "current_user_logins": current_user_logins,
        "login_chart_data": _build_login_chart_data(),
        "role_chart_data": _build_role_chart_data(),
        "user_rows": _build_user_rows() if request.user.is_staff else [],
    }

    return render(request, "dashboard.html", context)


@login_required
def chat_view(request):
    session = _get_session_for_request(request)

    if request.method == "POST":
        form = ChatForm(request.POST, request.FILES)

        if form.is_valid():
            message = (form.cleaned_data.get("message") or "").strip()
            attachment = form.cleaned_data.get("attachment")

            if not message and not attachment:
                form.add_error(None, "Enter a message or attach a file before sending.")
            else:
                user_message = ChatMessage.objects.create(
                    session=session,
                    role="user",
                    text=message,
                    attachment=attachment,
                )

                encoded_image = None
                mime_type = "image/jpeg"

                if user_message.attachment:
                    attachment_suffix = Path(user_message.attachment.name).suffix.lower()
                    if attachment_suffix in {".jpg", ".jpeg", ".png"}:
                        encoded_image, mime_type = encode_image(user_message.attachment.path)

                prompt_text = message or (
                    "The patient attached a file for context. Acknowledge the upload and explain "
                    "what additional details are needed to give a useful medical response."
                )

                try:
                    ai_response = analyze_image_with_query(
                        query=_build_chat_prompt(prompt_text),
                        encoded_image=encoded_image,
                        model=MEDICAL_MODEL,
                        mime_type=mime_type,
                    )
                except Exception:
                    ai_response = (
                        "I could not generate a response right now. Please try again in a moment."
                    )
                    messages.error(request, "The assistant could not generate a response right now.")

                ChatMessage.objects.create(
                    session=session,
                    role="assistant",
                    text=ai_response,
                )

                return redirect("chat")
    else:
        form = ChatForm()

    history = _serialize_history(session.messages.all().order_by("created_at"))
    return render(
        request,
        "chat.html",
        {
            "form": form,
            "history": history,
        },
    )


@login_required
def history_view(request):
    sessions = ChatSession.objects.filter(user=request.user).order_by("-created_at")
    session_id = request.GET.get("session_id")
    selected_session = sessions.filter(id=session_id).first() if session_id else sessions.first()
    messages_list = selected_session.messages.all().order_by("created_at") if selected_session else []

    return render(
        request,
        "history.html",
        {
            "sessions": sessions,
            "selected_session": selected_session,
            "messages": messages_list,
        },
    )


def login_view(request):
    ensure_demo_setup()

    if request.user.is_authenticated:
        return redirect("dashboard")

    requested_next = request.POST.get("next") or request.GET.get("next")
    next_url = (
        requested_next
        if requested_next
        and url_has_allowed_host_and_scheme(
            requested_next,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
        else reverse("dashboard")
    )
    form = LoginForm(request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        messages.success(request, "Welcome back. Your dashboard is ready.")
        return redirect(next_url)

    return render(
        request,
        "login.html",
        {
            "form": form,
            "next": next_url,
        },
    )


def register_view(request):
    ensure_demo_setup()

    if request.user.is_authenticated:
        return redirect("dashboard")

    form = RegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your account has been created successfully.")
        return redirect("dashboard")

    return render(
        request,
        "register.html",
        {
            "form": form,
        },
    )


@login_required
def change_credentials_view(request):
    profile_form = ProfileSettingsForm(instance=request.user, prefix="profile")
    password_form = PasswordChangeForm(request.user, prefix="password")

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "profile":
            profile_form = ProfileSettingsForm(request.POST, instance=request.user, prefix="profile")
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile details updated successfully.")
                return redirect("change_credentials")
        elif form_type == "password":
            password_form = PasswordChangeForm(request.user, request.POST, prefix="password")
            if password_form.is_valid():
                updated_user = password_form.save()
                update_session_auth_hash(request, updated_user)
                messages.success(request, "Password updated successfully.")
                return redirect("change_credentials")

    return render(
        request,
        "account_settings.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )


@staff_required
def dashboard_user_view(request, user_id):
    managed_user = get_object_or_404(user_model, pk=user_id)
    active_logins = managed_user.login_activities.filter(is_active=True)

    return render(
        request,
        "dashboard_user_view.html",
        {
            "managed_user": managed_user,
            "active_logins": active_logins,
            "locations": _get_user_locations(managed_user),
            "mobile_number": _get_mobile_number(managed_user),
        },
    )


@staff_required
def dashboard_user_edit(request, user_id):
    managed_user = get_object_or_404(user_model, pk=user_id)
    form = AdminUserManagementForm(request.POST or None, instance=managed_user)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "User details updated successfully.")
        return redirect("dashboard")

    return render(
        request,
        "dashboard_user_edit.html",
        {
            "managed_user": managed_user,
            "form": form,
        },
    )


@staff_required
def dashboard_user_delete(request, user_id):
    managed_user = get_object_or_404(user_model, pk=user_id)

    if request.method == "POST":
        if managed_user == request.user:
            messages.error(request, "You cannot delete your own administrator account.")
            return redirect("dashboard")

        managed_user.delete()
        messages.success(request, "User deleted successfully.")
        return redirect("dashboard")

    return render(
        request,
        "dashboard_user_delete.html",
        {
            "managed_user": managed_user,
        },
    )


def logout_view(request):
    _mark_current_login_inactive(request)
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("login")
