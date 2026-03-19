from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q
from django.utils.text import slugify

from .models import UserProfile

user_model = get_user_model()


TEXT_INPUT_ATTRS = {
    "autocomplete": "off",
}


def _build_unique_username(seed_value):
    base_username = slugify(seed_value).replace("-", "") or "member"
    candidate = base_username[:24]
    counter = 1

    while user_model.objects.filter(username__iexact=candidate).exists():
        suffix = str(counter)
        candidate = f"{base_username[: max(1, 24 - len(suffix) - 1)]}-{suffix}"
        counter += 1

    return candidate


class ChatForm(forms.Form):
    message = forms.CharField(
        label="Message",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "class": "auto-expand chat-input",
                "placeholder": "Describe symptoms, ask a follow-up question, or share any new changes.",
            }
        ),
    )
    attachment = forms.FileField(
        label="Attachment",
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".jpg,.jpeg,.png,.pdf",
            }
        ),
    )

    def clean_attachment(self):
        file = self.cleaned_data.get("attachment")
        if not file:
            return file

        if file.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File size must be under 5 MB.")

        allowed_types = {"jpg", "jpeg", "png", "pdf"}
        extension = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""

        if extension not in allowed_types:
            raise forms.ValidationError("Only JPG, JPEG, PNG, and PDF files are allowed.")

        return file


class LoginForm(forms.Form):
    login_id = forms.CharField(
        label="Email ID / User ID",
        widget=forms.TextInput(
            attrs={
                **TEXT_INPUT_ATTRS,
                "placeholder": "Enter your email ID or user ID",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user_cache = None

    def clean(self):
        cleaned_data = super().clean()
        login_id = (cleaned_data.get("login_id") or "").strip()
        password = cleaned_data.get("password")

        if not login_id or not password:
            return cleaned_data

        matched_user = user_model.objects.filter(
            Q(email__iexact=login_id) | Q(username__iexact=login_id)
        ).first()
        auth_username = matched_user.username if matched_user else login_id
        self.user_cache = authenticate(self.request, username=auth_username, password=password)

        if self.user_cache is None:
            raise forms.ValidationError("Enter a valid email/user ID and password.")

        if not self.user_cache.is_active:
            raise forms.ValidationError("This account is inactive.")

        return cleaned_data

    def get_user(self):
        return self.user_cache


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(
        label="First Name",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                **TEXT_INPUT_ATTRS,
                "placeholder": "Enter first name",
                "autocomplete": "given-name",
            }
        ),
    )
    last_name = forms.CharField(
        label="Last Name",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                **TEXT_INPUT_ATTRS,
                "placeholder": "Enter last name",
                "autocomplete": "family-name",
            }
        ),
    )
    email = forms.EmailField(
        label="Email ID",
        widget=forms.EmailInput(
            attrs={
                "placeholder": "Enter email ID",
                "autocomplete": "email",
            }
        ),
    )
    mobile_number = forms.CharField(
        label="Mobile Number",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                **TEXT_INPUT_ATTRS,
                "placeholder": "Enter mobile number",
                "autocomplete": "tel",
            }
        ),
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Create a password",
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Confirm your password",
                "autocomplete": "new-password",
            }
        ),
    )

    class Meta:
        model = user_model
        fields = ("first_name", "last_name", "email", "mobile_number", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if user_model.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_mobile_number(self):
        mobile_number = self.cleaned_data["mobile_number"].strip()
        digits = "".join(character for character in mobile_number if character.isdigit())
        if len(digits) < 10:
            raise forms.ValidationError("Enter a valid mobile number with at least 10 digits.")
        return digits

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data["email"].strip().lower()
        user.username = _build_unique_username(user.email.split("@")[0])

        if commit:
            user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={"mobile_number": self.cleaned_data["mobile_number"].strip()},
            )

        return user


class ProfileSettingsForm(forms.ModelForm):
    mobile_number = forms.CharField(
        label="Mobile Number",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                **TEXT_INPUT_ATTRS,
                "placeholder": "Update mobile number",
                "autocomplete": "tel",
            }
        ),
    )

    class Meta:
        model = user_model
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    **TEXT_INPUT_ATTRS,
                    "placeholder": "First name",
                    "autocomplete": "given-name",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    **TEXT_INPUT_ATTRS,
                    "placeholder": "Last name",
                    "autocomplete": "family-name",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "placeholder": "Email ID",
                    "autocomplete": "email",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            existing_profile = UserProfile.objects.filter(user=self.instance).first()
            self.fields["mobile_number"].initial = existing_profile.mobile_number if existing_profile else ""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if user_model.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def clean_mobile_number(self):
        mobile_number = self.cleaned_data["mobile_number"].strip()
        digits = "".join(character for character in mobile_number if character.isdigit())
        if len(digits) < 10:
            raise forms.ValidationError("Enter a valid mobile number with at least 10 digits.")
        return digits

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data["email"].strip().lower()

        if commit:
            user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={"mobile_number": self.cleaned_data["mobile_number"].strip()},
            )

        return user


class AdminUserManagementForm(ProfileSettingsForm):
    username = forms.CharField(label="User ID", disabled=True, required=False)
    is_staff = forms.BooleanField(label="Administrator role", required=False)
    is_active = forms.BooleanField(label="Active account", required=False)

    class Meta(ProfileSettingsForm.Meta):
        fields = ["first_name", "last_name", "email", "is_staff", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].initial = self.instance.username
