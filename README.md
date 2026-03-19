# AI-Powered Medical Assistant System

AI-Powered Medical Assistant System is a Django-based clinical decision-support platform for symptom intake, medical report analysis, image-assisted review, follow-up chat, dashboard analytics, user management, and audited treatment tracking.

## Highlights

- OTP-based registration with email and mobile verification
- AI-assisted medical report and image review
- Doctor treatment management with audit history
- Professional dashboard with activity and clinical analytics
- User management with device count and current login location visibility
- Branded responsive UI with dedicated clinical workflows
- Demo admin bootstrap for local setup

## Tech Stack

- Django
- Python
- SQLite
- HTML, CSS, JavaScript
- Groq-based AI integration
- Optional Twilio SMS delivery

## Quick Start

```bash
cd ai_medical_project
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py runserver
```

## Demo Credentials

- Username: `Admin`
- Password: `Admin123`

## Core Workflows

### Registration and OTP Verification

Users register with first name, last name, email, mobile number, and password. Account creation completes only after both the email OTP and mobile OTP are verified.

### Clinical Intake

Users can:

- Enter symptoms manually
- Upload audio for transcription
- Upload medical images
- Upload report files or report notes

The app stores analysis records for later comparison and treatment tracking.

### Follow-Up and Dashboard

- Continue patient conversations in the chat workspace
- Review saved session history
- Monitor dashboard analytics and risk distribution
- Track treatments with doctor details and timestamps
- Manage users, devices, roles, and locations as an administrator

## Environment Configuration

An example environment file is included at [`.env.example`](./.env.example).

Important settings:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `GROQ_API_KEY`
- `DJANGO_EMAIL_BACKEND`
- `DJANGO_SMS_BACKEND`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`

## OTP Delivery Notes

### Local Development

- Email OTPs can use Django's console email backend
- Mobile OTPs can use the console SMS backend
- In that mode, codes are printed to the server terminal/log output

### Real Delivery

To send real OTPs:

1. Configure SMTP settings and set `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
2. Configure Twilio credentials and set `DJANGO_SMS_BACKEND=twilio`

## Operations

- Health check endpoint: `/health/`
- Admin panel: `/admin/`
- Friendly custom error pages are included for 403, 404, and 500 responses

## Verification

Run the project checks and tests with:

```bash
python manage.py check
python manage.py test medical_app
```

## Professional Notes

- The platform is designed as a support tool for clinicians, not as a replacement for licensed medical judgment
- Emergency care decisions should always be handled through appropriate clinical and emergency channels
