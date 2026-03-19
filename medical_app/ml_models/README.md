Place optional trained model files in this directory to replace the heuristic fallback used by the application.

Supported file names:

- `report_classifier.pkl`
- `image_classifier.pkl`
- `report_classifier_metrics.json`

Useful management commands:

- `python manage.py sync_training_records`
- `python manage.py export_training_dataset --format jsonl`
- `python manage.py train_condition_model`
