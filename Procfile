web: gunicorn ai_medical_project.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 180
worker: python manage.py run_training_worker --continuous --poll-seconds 15
