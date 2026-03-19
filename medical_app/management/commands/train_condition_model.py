import pickle
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from medical_app.ml_baseline import train_frequency_condition_classifier
from medical_app.model_evaluation import (
    DEFAULT_RANDOM_SEED,
    DEFAULT_TRAIN_RATIO,
    EVALUATION_REPORT_PATH,
    build_training_samples,
    evaluate_condition_model,
    save_evaluation_report,
    split_training_samples,
)
from medical_app.models import TreatmentTrainingRecord


class Command(BaseCommand):
    help = "Train and evaluate a baseline condition-classification model using an 80/20 split."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(Path("medical_app") / "ml_models" / "report_classifier.pkl"),
            help="Path where the trained model pickle should be stored.",
        )
        parser.add_argument(
            "--minimum-records",
            type=int,
            default=3,
            help="Minimum number of approved records required before training runs.",
        )
        parser.add_argument(
            "--train-ratio",
            type=float,
            default=DEFAULT_TRAIN_RATIO,
            help="Training split ratio used for evaluation. Defaults to 0.8.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=DEFAULT_RANDOM_SEED,
            help="Random seed used for reproducible train/test splitting.",
        )
        parser.add_argument(
            "--metrics-output",
            default=str(EVALUATION_REPORT_PATH),
            help="Path where the evaluation metrics JSON should be stored.",
        )

    def handle(self, *args, **options):
        queryset = TreatmentTrainingRecord.objects.filter(is_approved=True).order_by("id")
        samples = build_training_samples(queryset)

        minimum_records = options["minimum_records"]
        if len(samples) < minimum_records:
            raise CommandError(
                f"At least {minimum_records} approved training records are required, only {len(samples)} found."
            )

        train_ratio = options["train_ratio"]
        if not 0 < train_ratio < 1:
            raise CommandError("The training ratio must be between 0 and 1.")

        seed = options["seed"]
        train_samples, test_samples = split_training_samples(samples, train_ratio=train_ratio, seed=seed)
        evaluation_model = train_frequency_condition_classifier(
            [(sample["text"], sample["label"]) for sample in train_samples]
        )
        evaluation_report = evaluate_condition_model(
            evaluation_model,
            train_samples,
            test_samples,
            train_ratio=train_ratio,
            seed=seed,
        )
        metrics_path = save_evaluation_report(evaluation_report, options["metrics_output"])

        # After evaluation, train the production model on the full approved dataset.
        model = train_frequency_condition_classifier(
            [(sample["text"], sample["label"]) for sample in samples]
        )
        output_path = Path(options["output"])
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("wb") as model_file:
            pickle.dump(model, model_file)

        train_percentage = round(train_ratio * 100)
        test_percentage = round((1 - train_ratio) * 100)
        self.stdout.write(
            self.style.SUCCESS(
                "Baseline condition model trained successfully with "
                f"{len(samples)} approved records at {output_path.as_posix()}. "
                f"Evaluation used an {train_percentage}/{test_percentage} split "
                f"and achieved {evaluation_report['accuracy_percent']}% accuracy on {evaluation_report['test_count']} test record(s). "
                f"Metrics saved to {metrics_path.as_posix()}."
            )
        )
