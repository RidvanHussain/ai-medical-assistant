from django.contrib.auth import get_user_model

from .models import FeaturedImage, UserProfile


DEFAULT_FEATURED_IMAGES = [
    {
        "title": "Dashboard Overview",
        "caption": "Open the analytics dashboard to review active sessions, user activity, and engagement trends.",
        "image_url": "https://images.unsplash.com/photo-1516321497487-e288fb19713f?auto=format&fit=crop&w=1200&q=80",
        "target_url": "/dashboard/",
        "display_order": 1,
    },
    {
        "title": "Clinical Follow-Up Chat",
        "caption": "Continue patient conversations, ask follow-up questions, and keep attachments with the case history.",
        "image_url": "https://images.unsplash.com/photo-1576091160550-2173dba999ef?auto=format&fit=crop&w=1200&q=80",
        "target_url": "/chat/",
        "display_order": 2,
    },
    {
        "title": "Patient History",
        "caption": "Review previously saved sessions, responses, and supporting files from a single timeline view.",
        "image_url": "https://images.unsplash.com/photo-1584982751601-97dcc096659c?auto=format&fit=crop&w=1200&q=80",
        "target_url": "/history/",
        "display_order": 3,
    },
]


def ensure_demo_admin():
    user_model = get_user_model()
    admin_user, created = user_model.objects.get_or_create(
        username="Admin",
        defaults={
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin@aimedical.local",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )

    changed = created
    if admin_user.email != "admin@aimedical.local":
        admin_user.email = "admin@aimedical.local"
        changed = True
    if admin_user.first_name != "Admin":
        admin_user.first_name = "Admin"
        changed = True
    if admin_user.last_name != "User":
        admin_user.last_name = "User"
        changed = True
    if not admin_user.is_staff:
        admin_user.is_staff = True
        changed = True
    if not admin_user.is_superuser:
        admin_user.is_superuser = True
        changed = True
    if not admin_user.is_active:
        admin_user.is_active = True
        changed = True
    if not admin_user.check_password("Admin123"):
        admin_user.set_password("Admin123")
        changed = True

    if changed:
        admin_user.save()

    UserProfile.objects.update_or_create(
        user=admin_user,
        defaults={
            "mobile_number": "9999999999",
            "last_known_location": "Demo environment",
        },
    )


def ensure_default_featured_images():
    if FeaturedImage.objects.exists():
        return

    FeaturedImage.objects.bulk_create([FeaturedImage(**item) for item in DEFAULT_FEATURED_IMAGES])


def ensure_demo_setup():
    ensure_demo_admin()
    ensure_default_featured_images()
