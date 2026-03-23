import csv
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from django.contrib.auth import get_user_model

from .models import MedicalAnalysis, TreatmentEntry, TreatmentTrainingRecord

User = get_user_model()


GENERIC_CONDITION_LABELS = {
    "general review required",
    "visual review suggested",
    "image model prediction",
    "unknown",
    "not specified",
    "n/a",
    "na",
    "none",
    "",
}

MIN_CONDITION_OCCURRENCES = 3


def normalize_condition_name(condition_str):
    """Normalize condition names for consistency and grouping."""
    if not condition_str:
        return None

    # Strip whitespace
    normalized = condition_str.strip()

    # Remove quotes and special characters
    normalized = re.sub(r'["\']', "", normalized)

    # Title case
    normalized = normalized.title()

    # Check if it's a generic label
    if normalized.lower() in GENERIC_CONDITION_LABELS:
        return None

    # Minimum length check
    if len(normalized) < 3:
        return None

    return normalized


def parse_medical_data_csv(csv_path):
    """
    Parse medical_data.csv.
    Columns: Patient_Problem, Disease, Prescription
    """
    records = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                problem = (row.get("Patient_Problem") or "").strip()
                disease = (row.get("Disease") or "").strip()
                prescription = (row.get("Prescription") or "").strip()

                if not problem or not disease:
                    continue

                condition = normalize_condition_name(disease)
                if not condition:
                    continue

                # Build input text
                input_text = f"Patient Problem: {problem}"
                if prescription:
                    input_text += f"\n\nPrescription: {prescription}"

                records.append({
                    "input_text": input_text,
                    "target_condition": condition,
                    "source": "medical_data.csv",
                })
    except Exception as e:
        print(f"Error parsing medical_data.csv: {e}")

    return records


def parse_diseases_symptoms_csv(csv_path):
    """
    Parse Diseases_Symptoms.csv.
    Columns: Name, Symptoms, Treatments, Disease_Code, Contagious, Chronic
    """
    records = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                disease_name = (row.get("Name") or "").strip()
                symptoms = (row.get("Symptoms") or "").strip()
                treatments = (row.get("Treatments") or "").strip()

                if not disease_name or (not symptoms and not treatments):
                    continue

                condition = normalize_condition_name(disease_name)
                if not condition:
                    continue

                # Build input text
                input_text = ""
                if symptoms:
                    input_text += f"Symptoms: {symptoms}"
                if treatments:
                    if input_text:
                        input_text += "\n\n"
                    input_text += f"Treatments: {treatments}"

                if not input_text.strip():
                    continue

                records.append({
                    "input_text": input_text,
                    "target_condition": condition,
                    "source": "Diseases_Symptoms.csv",
                })
    except Exception as e:
        print(f"Error parsing Diseases_Symptoms.csv: {e}")

    return records


def parse_train_csv(csv_path):
    """
    Parse train.csv (Q&A format).
    Columns: qtype, Question, Answer
    """
    records = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                qtype = (row.get("qtype") or "").strip()
                question = (row.get("Question") or "").strip()
                answer = (row.get("Answer") or "").strip()

                if not question or not answer:
                    continue

                # Extract condition from qtype or question/answer context
                condition = None

                # Try to extract from qtype or common disease patterns
                if qtype and qtype.lower() not in {"unknown", "other", "general"}:
                    potential_condition = normalize_condition_name(qtype)
                    if potential_condition:
                        condition = potential_condition

                # If no condition found, skip (too generic)
                if not condition:
                    continue

                # Build input text from question and answer
                input_text = f"Question: {question}\n\nAnswer: {answer[:500]}"

                records.append({
                    "input_text": input_text,
                    "target_condition": condition,
                    "source": "train.csv",
                })
    except Exception as e:
        print(f"Error parsing train.csv: {e}")

    return records


def parse_chatbot_csv(csv_path, sample_ratio=0.1):
    """
    Parse ai-medical-chatbot.csv (Patient-Doctor conversations).
    Columns: Description, Patient, Doctor
    Sample 10% of records to manage memory.
    """
    records = []
    all_records = []

    try:
        with open(csv_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                description = (row.get("Description") or "").strip()
                patient = (row.get("Patient") or "").strip()
                doctor = (row.get("Doctor") or "").strip()

                if not patient or not doctor:
                    continue

                all_records.append({
                    "description": description,
                    "patient": patient,
                    "doctor": doctor,
                })

        # Sample 10% of records
        sample_size = max(1, int(len(all_records) * sample_ratio))
        sampled = random.sample(all_records, min(sample_size, len(all_records)))

        for row in sampled:
            description = row["description"]
            patient = row["patient"]
            doctor = row["doctor"]

            # Extract potential condition from description or doctor response
            condition = None

            # Try to extract from description
            if description:
                # Look for common disease patterns
                potential = normalize_condition_name(description.split(":")[0])
                if potential:
                    condition = potential

            # If still no condition, try to extract from doctor's response
            if not condition and doctor:
                # Look for mentioned conditions in doctor response
                # This is heuristic - we look for capitalized words that might be conditions
                words = doctor.split()
                for word in words[:50]:  # Check first 50 words
                    if word[0].isupper() and len(word) > 4:
                        potential = normalize_condition_name(word)
                        if potential:
                            condition = potential
                            break

            if not condition:
                continue

            # Build input text
            input_text = f"Patient Query: {patient[:300]}\n\nDoctor Response: {doctor[:400]}"

            records.append({
                "input_text": input_text,
                "target_condition": condition,
                "source": "ai-medical-chatbot.csv",
            })

    except Exception as e:
        print(f"Error parsing ai-medical-chatbot.csv: {e}")

    return records


def parse_medical_questions_csv(csv_path):
    """
    Parse medical_question_answer_dataset_50000.csv.
    Columns: ID, Symptoms/Question, Disease Prediction, Recommended Medicines, Advice
    """
    records = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                question = (row.get("Symptoms/Question") or "").strip()
                disease = (row.get("Disease Prediction") or "").strip()
                advice = (row.get("Advice") or "").strip()
                medicines = (row.get("Recommended Medicines") or "").strip()

                if not question or not disease:
                    continue

                condition = normalize_condition_name(disease)
                if not condition:
                    continue

                # Build input text
                input_text = f"Symptoms: {question}"
                if medicines:
                    input_text += f"\n\nMedicines: {medicines}"
                if advice:
                    input_text += f"\n\nAdvice: {advice}"

                records.append({
                    "input_text": input_text,
                    "target_condition": condition,
                    "source": "medical_question_answer_dataset_50000.csv",
                })
    except Exception as e:
        print(f"Error parsing medical_question_answer_dataset_50000.csv: {e}")

    return records


def filter_by_minimum_occurrences(records, min_count=MIN_CONDITION_OCCURRENCES):
    """Filter records to only include conditions with minimum occurrences."""
    condition_counts = Counter(r["target_condition"] for r in records)
    valid_conditions = {c for c, count in condition_counts.items() if count >= min_count}
    return [r for r in records if r["target_condition"] in valid_conditions]


def create_training_records_batch(records, dry_run=False, replace=False, verbose=False):
    """
    Create TreatmentTrainingRecord entries from parsed records.
    Creates associated MedicalAnalysis and TreatmentEntry objects as required.
    Returns a dict with statistics about created records.
    """
    stats = {
        "total_records": len(records),
        "created": 0,
        "skipped": 0,
        "condition_distribution": defaultdict(int),
    }

    if not records:
        return stats

    # Get default user for added_by field
    default_user = User.objects.first()
    if not default_user:
        print("Warning: No users found in database. Cannot create training records.")
        return stats

    if replace and not dry_run:
        # Delete existing imported records (cascade deletes related objects)
        deleted_count, _ = TreatmentTrainingRecord.objects.filter(
            source_type="external_dataset"
        ).delete()
        if verbose:
            print(f"[Cleanup] Deleted {deleted_count} existing imported records")

    if dry_run:
        # Just count conditions without saving
        for record in records:
            stats["condition_distribution"][record["target_condition"]] += 1
            stats["created"] += 1
        return stats

    # Create records with associated objects in batches
    batch_size = 500
    for batch_start in range(0, len(records), batch_size):
        batch_end = min(batch_start + batch_size, len(records))
        batch_records = records[batch_start:batch_end]

        # Create MedicalAnalysis objects
        analyses_to_create = [
            MedicalAnalysis(
                title=f"Imported: {rec['target_condition']}",
                symptoms_text=rec["input_text"][:500],
                predicted_condition=rec["target_condition"],
                risk_level="Medium",
                confidence_score=0.75,
                detected_conditions_count=1,
                model_source="imported",
            )
            for rec in batch_records
        ]
        created_analyses = MedicalAnalysis.objects.bulk_create(analyses_to_create)

        # Create TreatmentEntry objects
        treatments_to_create = [
            TreatmentEntry(
                analysis=analysis,
                doctor_name="Data Import",
                doctor_id="import",
                specialization="Medical AI Training",
                treatment_notes=f"Imported from {batch_records[i]['source']}",
                added_by=default_user,
            )
            for i, analysis in enumerate(created_analyses)
        ]
        created_treatments = TreatmentEntry.objects.bulk_create(treatments_to_create)

        # Create TreatmentTrainingRecord objects
        training_records_to_create = [
            TreatmentTrainingRecord(
                treatment=treatment,
                analysis=treatment.analysis,
                source_type="external_dataset",
                input_text=batch_records[i]["input_text"],
                target_condition=batch_records[i]["target_condition"],
                target_specialization="Medical AI Training",
                target_treatment=f"Medical training data from {batch_records[i]['source']}",
                quality_score=70,
                is_approved=True,
                review_notes=f"Imported from {batch_records[i]['source']}",
                feature_snapshot={
                    "source": batch_records[i]["source"],
                    "imported": True,
                },
            )
            for i, treatment in enumerate(created_treatments)
        ]
        TreatmentTrainingRecord.objects.bulk_create(training_records_to_create)

        # Update stats
        for record in batch_records:
            stats["condition_distribution"][record["target_condition"]] += 1
        stats["created"] += len(training_records_to_create)

    return stats


def import_all_datasets(datasets_dir, dry_run=False, replace=False, verbose=False):
    """
    Load and parse all 5 external datasets.
    Returns combined records and statistics.
    """
    datasets_dir = Path(datasets_dir).expanduser()

    all_records = []
    stats = {
        "medical_data.csv": {"found": False, "records": 0},
        "Diseases_Symptoms.csv": {"found": False, "records": 0},
        "train.csv": {"found": False, "records": 0},
        "ai-medical-chatbot.csv": {"found": False, "records": 0},
        "medical_question_answer_dataset_50000.csv": {"found": False, "records": 0},
    }

    # Parse medical_data.csv
    medical_data_path = datasets_dir / "medical_data.csv"
    if medical_data_path.exists():
        records = parse_medical_data_csv(medical_data_path)
        all_records.extend(records)
        stats["medical_data.csv"]["found"] = True
        stats["medical_data.csv"]["records"] = len(records)
        if verbose:
            print("+ Loaded medical_data.csv: {} records".format(len(records)))

    # Parse Diseases_Symptoms.csv
    diseases_path = datasets_dir / "Diseases_Symptoms.csv"
    if diseases_path.exists():
        records = parse_diseases_symptoms_csv(diseases_path)
        all_records.extend(records)
        stats["Diseases_Symptoms.csv"]["found"] = True
        stats["Diseases_Symptoms.csv"]["records"] = len(records)
        if verbose:
            print("+ Loaded Diseases_Symptoms.csv: {} records".format(len(records)))

    # Parse train.csv
    train_path = datasets_dir / "train.csv"
    if train_path.exists():
        records = parse_train_csv(train_path)
        all_records.extend(records)
        stats["train.csv"]["found"] = True
        stats["train.csv"]["records"] = len(records)
        if verbose:
            print("+ Loaded train.csv: {} records".format(len(records)))

    # Parse ai-medical-chatbot.csv
    chatbot_path = datasets_dir / "ai-medical-chatbot.csv"
    if chatbot_path.exists():
        records = parse_chatbot_csv(chatbot_path, sample_ratio=0.1)
        all_records.extend(records)
        stats["ai-medical-chatbot.csv"]["found"] = True
        stats["ai-medical-chatbot.csv"]["records"] = len(records)
        if verbose:
            print("+ Loaded ai-medical-chatbot.csv: {} records (10% sample)".format(len(records)))

    # Parse medical_question_answer_dataset_50000.csv
    questions_path = datasets_dir / "medical_question_answer_dataset_50000.csv"
    if questions_path.exists():
        records = parse_medical_questions_csv(questions_path)
        all_records.extend(records)
        stats["medical_question_answer_dataset_50000.csv"]["found"] = True
        stats["medical_question_answer_dataset_50000.csv"]["records"] = len(records)
        if verbose:
            print("+ Loaded medical_question_answer_dataset_50000.csv: {} records".format(len(records)))

    if verbose:
        print("\n[Preprocessing] Total records before filtering: {}".format(len(all_records)))

    # Filter by minimum occurrences
    filtered_records = filter_by_minimum_occurrences(all_records, MIN_CONDITION_OCCURRENCES)
    if verbose:
        filtered_count = len(all_records) - len(filtered_records)
        print("[Preprocessing] Filtered out {} records (condition too sparse)".format(filtered_count))
        print("[Preprocessing] Records after filtering: {}".format(len(filtered_records)))

    return filtered_records, stats
