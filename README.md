# AI-Powered Medical Assistant System

AI-Powered Medical Assistant System is a Django-based clinical decision-support platform for symptom intake, medical report analysis, image-assisted review, follow-up chat, dashboard analytics, user management, admin-curated medical knowledge, and background ML retraining.

## Highlights

- OTP-based registration with email and mobile verification
- Username/email login plus optional Gmail login through Google OAuth
- Full multilingual website behavior for the main user-facing experience
- AI-assisted symptom, report, image, and follow-up workflows
- Local TF-IDF + Logistic Regression condition classifier
- Local TF-IDF QA retriever with Groq fallback for low-confidence chat
- Doctor treatment logging and training-record generation
- Admin bulk dataset upload with warning preview and error CSV export
- Developer-only training control center with secure `Train Now` workflow
- Background training queue so heavy retraining stays outside normal HTTP requests
- Dashboard analytics, history timeline, and account preferences
- WhiteNoise static optimization, cached selectors, and runtime model caching

## Supported Website Languages

The main website now behaves as a multilingual product instead of only changing AI response language.

Currently supported user-facing languages:

- English
- Hindi
- Urdu
- Arabic
- Bengali

When the user changes website language, the system aligns:

- major UI labels and user-facing text
- AI prompt language
- voice-summary language behavior
- speech-to-text language hint
- text direction for RTL languages such as Urdu and Arabic

## Tech Stack

- Python 3.12
- Django 6.0.3
- SQLite
- HTML, CSS, JavaScript
- Groq API
- scikit-learn
- django-allauth
- WhiteNoise
- Pillow
- SpeechRecognition
- pydub
- edge-tts

## Quick Start

```bash
cd ai_medical_project
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py bootstrap_defaults
python manage.py runserver
```

If you want queued ML refresh jobs to process automatically, keep the training worker running in a second terminal:

```bash
cd ai_medical_project
python manage.py run_training_worker --continuous
```

## Demo Credentials

- Username: `Admin`
- Password: `Admin123`

## Core Workflows

### Clinical Intake

Users can:

- enter symptoms manually
- upload audio for transcription
- upload a medical image
- upload current report notes or files
- upload previous report notes or files for comparison

The system stores each case as a structured `MedicalAnalysis` record for later review, comparison, and treatment tracking.

### Reports and Comparison

The reports workspace supports:

- current report interpretation
- previous-vs-current report comparison
- disease percentage comparison where possible
- saved clinical records for dashboard and history views

### Follow-Up Chat

The chat workspace supports:

- persistent conversations
- attachment-aware clinical discussion
- local QA retrieval for text-only questions
- Groq fallback when local retrieval confidence is low

### Dashboard and History

The dashboard and history pages provide:

- quick actions
- recent analyses
- risk and condition analytics
- treatment and knowledge visibility
- history timeline navigation
- staff-only training-status visibility for approved developer admins

## Authentication and Access

### OTP Registration

New users register with first name, last name, email, mobile number, and password. Account creation completes only after both the email OTP and mobile OTP are verified.

### Gmail Login

The login page supports Google OAuth so users can continue with Gmail like other modern websites.

To enable it:

1. Create a Google OAuth Web application in Google Cloud Console.
2. Add local redirect URIs such as:
   - `http://127.0.0.1:8000/accounts/google/login/callback/`
   - `http://localhost:8000/accounts/google/login/callback/`
3. Set `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` in `.env`.
4. Restart the server.

When configured, clicking `Login with Gmail` opens the Google account chooser directly. If the browser is already signed into Google, the user can continue with one click.

### Developer-Only Training Access

High-volume ML controls are intentionally restricted:

- superusers always have access
- normal users do not see training controls
- staff users need explicit developer training access to use the secure training console

This keeps bulk import and retraining under controlled credentials.

## AI / ML Pipeline

### Generative AI Layer

Groq-powered prompting is used for:

- clinical summaries
- follow-up answers
- structured report interpretation
- image-assisted medical review
- multilingual response alignment

### Local Condition Classifier

The report-condition classifier uses:

- TF-IDF vectorization
- Logistic Regression
- deduplicated clean datasets
- label normalization
- persisted model artifacts
- heuristic fallback when the trained model is unavailable or less trustworthy

Evaluation snapshot:

- filtered records: `308`
- train split: `246`
- test split: `62`
- accuracy: `51.61%`
- macro F1: `0.3709`
- weighted F1: `0.4249`

### Local QA Ranker

The QA subsystem uses TF-IDF retrieval over clean and curated question-answer data.

Evaluation snapshot:

- raw clean entries: `50,812`
- deduplicated entries: `832`
- duplicates removed: `49,980`
- test entries: `167`
- Hit@1: `0.6%`

### Admin-Driven Continuous Learning

The final system supports a controlled supervised-learning loop:

1. Doctors add treatment entries to analyses.
2. Approved treatment entries become structured training records.
3. Admins add manual clinical knowledge or bulk-upload CSV/ZIP datasets.
4. Approved knowledge increases the pending retraining count.
5. Once the configured threshold is reached, a queued training job is created.
6. The background worker processes the job and refreshes model artifacts.
7. Metrics and run history are stored as versioned training records.

## Admin Knowledge and Training Operations

The admin panel includes dedicated ML operations models:

- `AI Model Configuration`
- `Clinical Knowledge Entry`
- `Training Dataset Upload`
- `AI Training Run`

Available capabilities:

- configure runtime model parameters such as `temperature`, `top_p`, and token limits
- add manual knowledge entries
- upload large CSV or ZIP datasets
- download import template CSV
- download sample ZIP packs with multiple CSV examples
- review warning previews and error CSV files
- trigger `Train Now`
- track queued, running, successful, or failed training runs

Useful commands:

```bash
python manage.py bootstrap_defaults
python manage.py import_external_datasets --datasets-dir %USERPROFILE%\\Downloads --replace --dedupe
python manage.py sync_training_records
python manage.py export_training_dataset --format jsonl
python manage.py train_condition_model
python manage.py train_qa_ranker --datasets-dir %USERPROFILE%\\Downloads --dedupe
python manage.py refresh_ai_models --reason "manual refresh"
python manage.py refresh_ai_models --queue --reason "queued refresh"
python manage.py run_training_worker --once
python manage.py run_training_worker --continuous
```

## Performance and Optimization

Optimization work already implemented includes:

- default record seeding moved out of normal request flow
- Django `LocMemCache` for read-mostly dashboard and homepage data
- WhiteNoise compression and static cache headers
- selector-based query composition for read-heavy pages
- reduced repeated `count()` patterns through aggregate summaries
- throttled login-activity writes
- file-mtime based ML artifact caching
- runtime QA retriever caching
- duplicate report-analysis avoidance within one intake request
- narrowed duplicate-detection query scope during bulk imports
- background queue for large retraining jobs
- database indexes on hot paths

## Environment Configuration

An example environment file is included at [`.env.example`](./.env.example).

Important settings include:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `GROQ_API_KEY`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `DJANGO_EMAIL_BACKEND`
- `DJANGO_SMS_BACKEND`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `DJANGO_DEFAULT_PHONE_COUNTRY_CODE`

## OTP Delivery Notes

### Local Development

- Email OTPs can use Django's console email backend.
- Mobile OTPs can use the console SMS backend.
- In that mode, codes are printed to server output.

### Real Delivery

To send real OTPs:

1. Configure SMTP settings and set `DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
2. Configure Twilio credentials and set `DJANGO_SMS_BACKEND=twilio`
3. Set `DJANGO_DEFAULT_PHONE_COUNTRY_CODE` if users enter local numbers without a `+` prefix

## Operations

- Health check endpoint: `/health/`
- Admin panel: `/admin/`
- Developer training center: available to approved developer admins from the dashboard/admin flow
- Friendly custom error pages for 403, 404, and 500 responses are included

## Verification

Run validation with:

```bash
python manage.py check
python manage.py test medical_app
```

Current validation snapshot:

- `python manage.py check` passes
- `python manage.py test medical_app` passes with **71 / 71 tests**

## Major Project Report

A separate hard-copy report workspace is available outside the project source tree:

- [Major Project Report Markdown](../major_project_report/AI_Medical_Assistant_Major_Project_Report.md)
- [Major Project Report HTML](../major_project_report/AI_Medical_Assistant_Major_Project_Report.html)
- [Major Project Report RTF](../major_project_report/AI_Medical_Assistant_Major_Project_Report.rtf)
- [Report Notes](../major_project_report/README_PRINT.txt)

The Markdown report is the latest editable source and has been updated to reflect:

- multilingual website behavior
- admin-curated learning pipeline
- background training queue
- developer-only training console
- optimization work
- current validation status

## Professional Notes

- The platform is designed as a support tool for clinicians and students, not as a replacement for licensed medical judgment.
- Emergency care decisions should always be handled through appropriate clinical or emergency channels.
