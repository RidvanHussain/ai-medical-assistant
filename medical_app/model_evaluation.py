import json
import random
from pathlib import Path

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .analysis_engine import MODEL_DIR


DEFAULT_TRAIN_RATIO = 0.8
DEFAULT_RANDOM_SEED = 42
EVALUATION_REPORT_PATH = MODEL_DIR / "report_classifier_metrics.json"


def build_training_samples(queryset):
    return [
        {
            "record_id": record.id,
            "text": record.input_text.strip(),
            "label": record.target_condition.strip(),
        }
        for record in queryset
        if record.input_text.strip() and record.target_condition.strip()
    ]


def split_training_samples(samples, train_ratio=DEFAULT_TRAIN_RATIO, seed=DEFAULT_RANDOM_SEED):
    if len(samples) < 2:
        raise ValueError("At least 2 samples are required for an 80/20 evaluation split.")

    shuffled_samples = list(samples)
    random.Random(seed).shuffle(shuffled_samples)

    test_count = max(1, int(round(len(shuffled_samples) * (1 - train_ratio))))
    if test_count >= len(shuffled_samples):
        test_count = len(shuffled_samples) - 1

    train_count = len(shuffled_samples) - test_count
    if train_count < 1:
        raise ValueError("At least 1 training sample is required after splitting the dataset.")

    return shuffled_samples[:train_count], shuffled_samples[train_count:]


def build_label_distribution(samples):
    distribution = {}
    for sample in samples:
        distribution[sample["label"]] = distribution.get(sample["label"], 0) + 1
    return distribution


def evaluate_condition_model(model, train_samples, test_samples, train_ratio=DEFAULT_TRAIN_RATIO, seed=DEFAULT_RANDOM_SEED):
    predictions = model.predict([sample["text"] for sample in test_samples])
    test_results = []
    correct_predictions = 0

    for sample, predicted_label in zip(test_samples, predictions):
        is_correct = predicted_label == sample["label"]
        if is_correct:
            correct_predictions += 1

        test_results.append(
            {
                "record_id": sample["record_id"],
                "actual_label": sample["label"],
                "predicted_label": str(predicted_label),
                "is_correct": is_correct,
            }
        )

    accuracy = correct_predictions / len(test_samples) if test_samples else 0

    return {
        "evaluated_at": timezone.now().isoformat(),
        "train_ratio": train_ratio,
        "test_ratio": round(1 - train_ratio, 2),
        "seed": seed,
        "total_records": len(train_samples) + len(test_samples),
        "train_count": len(train_samples),
        "test_count": len(test_samples),
        "correct_predictions": correct_predictions,
        "accuracy": round(accuracy, 4),
        "accuracy_percent": round(accuracy * 100, 2),
        "train_distribution": build_label_distribution(train_samples),
        "test_distribution": build_label_distribution(test_samples),
        "test_results": test_results,
    }


def save_evaluation_report(report, output_path=EVALUATION_REPORT_PATH):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as report_file:
        json.dump(report, report_file, ensure_ascii=True, indent=2)
    return output_path


def load_evaluation_report(output_path=EVALUATION_REPORT_PATH):
    output_path = Path(output_path)
    if not output_path.exists():
        return None

    with output_path.open("r", encoding="utf-8") as report_file:
        report = json.load(report_file)

    evaluated_at = parse_datetime(report.get("evaluated_at") or "")
    if evaluated_at:
        if timezone.is_naive(evaluated_at):
            evaluated_at = timezone.make_aware(evaluated_at, timezone.get_current_timezone())
        report["evaluated_at_datetime"] = timezone.localtime(evaluated_at)

    return report
