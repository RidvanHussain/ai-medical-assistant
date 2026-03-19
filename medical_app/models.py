from django.conf import settings
from django.db import models


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
