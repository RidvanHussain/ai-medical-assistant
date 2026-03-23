import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from medical_app.dataset_importer import import_all_datasets, create_training_records_batch
from medical_app.model_evaluation import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_TRAIN_RATIO,
    build_training_samples,
    evaluate_condition_model,
    save_evaluation_report,
    split_training_samples,
)
from medical_app.ml_baseline import train_frequency_condition_classifier
from medical_app.models import TreatmentTrainingRecord


class Command(BaseCommand):
    help = (
        "Import external medical datasets and train condition classification model. "
        "Loads 5 datasets (medical_data.csv, Diseases_Symptoms.csv, train.csv, "
        "ai-medical-chatbot.csv, medical_question_answer_dataset_50000.csv) from a directory, "
        "creates training records, and optionally trains the condition model."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--datasets-dir",
            type=str,
            default=str(Path.home() / "Downloads"),
            help="Path to directory containing CSV files (default: ~/Downloads)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview records without saving to database",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing imported records before import",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Show detailed progress output",
        )
        parser.add_argument(
            "--no-train",
            action="store_true",
            help="Import data only, do not train model",
        )
        parser.add_argument(
            "--train-ratio",
            type=float,
            default=DEFAULT_TRAIN_RATIO,
            help="Training split ratio (default: 0.8)",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=DEFAULT_RANDOM_SEED,
            help="Random seed for reproducibility (default: 42)",
        )

    def handle(self, *args, **options):
        datasets_dir = options["datasets_dir"]
        dry_run = options["dry_run"]
        replace = options["replace"]
        verbose = options["verbose"]
        no_train = options["no_train"]
        train_ratio = options["train_ratio"]
        seed = options["seed"]

        # Validate path
        datasets_path = Path(datasets_dir)
        if not datasets_path.exists():
            raise CommandError("Datasets directory not found: {}".format(datasets_dir))

        self.stdout.write(self.style.SUCCESS("\n[IMPORT PHASE]"))
        self.stdout.write("Loading datasets from: {}".format(datasets_dir))

        if dry_run:
            self.stdout.write("(DRY RUN - no changes will be saved)")
        if replace:
            self.stdout.write(self.style.WARNING("(REPLACE mode - existing imports will be deleted)"))

        # Load and parse all datasets
        try:
            all_records, load_stats = import_all_datasets(
                datasets_dir,
                dry_run=dry_run,
                replace=replace,
                verbose=verbose,
            )
        except Exception as e:
            raise CommandError("Error loading datasets: {}".format(e))

        if not all_records:
            raise CommandError("No valid records found in datasets")

        if verbose:
            self.stdout.write("")
            self.stdout.write("Dataset loading summary:")
            for dataset_name, stats in load_stats.items():
                if stats["found"]:
                    self.stdout.write(
                        self.style.SUCCESS("  [OK] {}: {} records".format(dataset_name, stats['records']))
                    )
                else:
                    self.stdout.write("  [--] {}: not found".format(dataset_name))

        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Total records loaded: {}".format(len(all_records))))

        if dry_run:
            # Show preview of conditions
            self.stdout.write("\nCondition distribution (preview):")
            from collections import Counter

            condition_counts = Counter(r["target_condition"] for r in all_records)
            for condition, count in condition_counts.most_common(10):
                self.stdout.write("  - {}: {}".format(condition, count))
            if len(condition_counts) > 10:
                self.stdout.write("  ... and {} more conditions".format(len(condition_counts) - 10))

            self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Dry run complete (would create {} records)".format(len(all_records))))
            return

        # Create training records in database
        self.stdout.write("\nCreating training records in database...")
        try:
            creation_stats = create_training_records_batch(
                all_records,
                dry_run=False,
                replace=replace,
                verbose=verbose,
            )
        except Exception as e:
            raise CommandError("Error creating training records: {}".format(e))

        self.stdout.write(
            self.style.SUCCESS("[OK] Created {} approved training records".format(creation_stats['created']))
        )

        # Show condition distribution
        if verbose:
            self.stdout.write("\nCondition distribution:")
            for condition, count in sorted(creation_stats["condition_distribution"].items(), key=lambda x: x[1], reverse=True)[:15]:
                self.stdout.write("  - {}: {}".format(condition, count))
            if len(creation_stats["condition_distribution"]) > 15:
                self.stdout.write(
                    "  ... and {} more conditions".format(len(creation_stats['condition_distribution']) - 15)
                )

        # Train model if requested
        if no_train:
            self.stdout.write(
                self.style.SUCCESS("\n[OK] Data import complete (training skipped)")
            )
            return

        self.stdout.write(self.style.SUCCESS("\n[TRAINING PHASE]"))
        self.stdout.write("Querying all approved records from database...")

        queryset = TreatmentTrainingRecord.objects.filter(is_approved=True).order_by("id")
        samples = build_training_samples(queryset)

        if len(samples) < 3:
            raise CommandError(
                "At least 3 approved training records required for training, found {}".format(len(samples))
            )

        self.stdout.write(self.style.SUCCESS("[OK] Found {} approved records".format(len(samples))))

        # Validate train ratio
        if not 0 < train_ratio < 1:
            raise CommandError("Training ratio must be between 0 and 1")

        # Split data
        self.stdout.write("Splitting data (80/20)...")
        train_samples, test_samples = split_training_samples(
            samples, train_ratio=train_ratio, seed=seed
        )
        self.stdout.write(
            self.style.SUCCESS(
                "[OK] Train: {} | Test: {}".format(len(train_samples), len(test_samples))
            )
        )

        # Train evaluation model
        self.stdout.write("Training classifier on training set...")
        evaluation_model = train_frequency_condition_classifier(
            [(sample["text"], sample["label"]) for sample in train_samples]
        )
        self.stdout.write(self.style.SUCCESS("[OK] Classifier trained"))

        # Evaluate
        self.stdout.write("Evaluating model on test set...")
        evaluation_report = evaluate_condition_model(
            evaluation_model,
            train_samples,
            test_samples,
            train_ratio=train_ratio,
            seed=seed,
        )

        accuracy_percent = evaluation_report["accuracy_percent"]
        self.stdout.write(
            self.style.SUCCESS("[OK] Test set accuracy: {}%".format(accuracy_percent))
        )

        # Train production model on full dataset
        self.stdout.write("Training final model on full dataset...")
        production_model = train_frequency_condition_classifier(
            [(sample["text"], sample["label"]) for sample in samples]
        )

        # Save model and metrics
        import pickle

        output_path = Path("medical_app") / "ml_models" / "report_classifier.pkl"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("wb") as model_file:
            pickle.dump(production_model, model_file)

        metrics_output = Path("medical_app") / "ml_models" / "report_classifier_metrics.json"
        save_evaluation_report(evaluation_report, str(metrics_output))

        self.stdout.write(self.style.SUCCESS("[OK] Model saved to: {}".format(output_path)))
        self.stdout.write(self.style.SUCCESS("[OK] Metrics saved to: {}".format(metrics_output)))

        # Show summary
        self.stdout.write(self.style.SUCCESS("\n[RESULTS]"))
        self.stdout.write("Total imported records: {}".format(creation_stats['created']))
        self.stdout.write("Unique conditions: {}".format(len(creation_stats['condition_distribution'])))
        self.stdout.write("Model accuracy on test set: {}%".format(accuracy_percent))
        self.stdout.write("Training records: {}".format(len(train_samples)))
        self.stdout.write("Test records: {}".format(len(test_samples)))

        train_percentage = round(train_ratio * 100)
        test_percentage = round((1 - train_ratio) * 100)

        self.stdout.write(
            self.style.SUCCESS(
                "\n[OK] Import and training complete! "
                "Model achieved {}% accuracy on {}% test set "
                "using {} approved records with {} unique conditions.".format(
                    accuracy_percent,
                    test_percentage,
                    len(samples),
                    len(creation_stats['condition_distribution'])
                )
            )
        )
