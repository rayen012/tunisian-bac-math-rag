#!/usr/bin/env python3
"""
generate_grading_sheets.py
--------------------------
Takes evaluation results JSON and produces:
  1. blind_grading_sheet.json  — Anonymized answers (System X/Y/Z) for teachers
  2. answer_key.json           — Reveals which system is which (keep SECRET)
  3. grading_template.json     — Pre-filled template with empty scores for teachers

The teacher sees questions + 3 anonymized answers and scores each on 6 criteria.
After grading, you reveal the answer key and analyze results.

Usage:
  python evaluation/generate_grading_sheets.py
  python evaluation/generate_grading_sheets.py --input evaluation/results/eval_results_latest.json
"""

import argparse
import json
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Grading rubric — 6 criteria, each scored 0-5
GRADING_RUBRIC = {
    "mathematical_correctness": {
        "description": "Les calculs et raisonnements mathématiques sont-ils corrects ?",
        "weight": 5,
        "scale": "0-5 (0=tout faux, 5=parfait)",
    },
    "formal_rigor": {
        "description": "La rédaction suit-elle les conventions formelles (On a..., Donc..., D'après...) ?",
        "weight": 5,
        "scale": "0-5",
    },
    "bac_style_alignment": {
        "description": "La réponse ressemble-t-elle à une correction officielle du Bac tunisien ?",
        "weight": 3,
        "scale": "0-5",
    },
    "clarity_and_structure": {
        "description": "La réponse est-elle bien organisée, claire, facile à suivre ?",
        "weight": 3,
        "scale": "0-5",
    },
    "pedagogical_quality": {
        "description": "La réponse aide-t-elle l'élève à comprendre (pas juste donner la réponse) ?",
        "weight": 2,
        "scale": "0-5",
    },
    "hallucination_penalty": {
        "description": "Y a-t-il des erreurs inventées, des théorèmes inexistants, ou des méthodes hors programme ?",
        "weight": 2,
        "scale": "0=hallucinations graves, 5=aucune hallucination",
    },
}


def generate_sheets(results_path: Path):
    """Generate blind grading sheets from evaluation results."""
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data["results"]
    metadata = data["metadata"]

    # Filter out guardrail questions (E category) — they get a separate pass/fail
    graded_results = [r for r in results if r["category"] != "E"]
    guardrail_results = [r for r in results if r["category"] == "E"]

    random.seed(42)  # Reproducible shuffling

    blind_sheets = []
    answer_key = []
    system_names = ["RAG", "PROMPT_ONLY", "HYBRID"]
    blind_labels = ["Système X", "Système Y", "Système Z"]

    for entry in graded_results:
        # Randomly assign systems to X/Y/Z labels
        shuffled = list(system_names)
        random.shuffle(shuffled)

        sheet = {
            "question_id": entry["question_id"],
            "category": entry["category"],
            "chapter": entry["chapter"],
            "mode": entry["mode"],
            "question": entry["question"],
            "answers": {},
        }

        for label, sys_name in zip(blind_labels, shuffled):
            sys_data = entry["systems"].get(sys_name, {})
            sheet["answers"][label] = sys_data.get("answer", "[ERREUR: pas de réponse]")

        blind_sheets.append(sheet)

        answer_key.append({
            "question_id": entry["question_id"],
            "Système X": shuffled[0],
            "Système Y": shuffled[1],
            "Système Z": shuffled[2],
        })

    # ── Grading template (what the teacher fills in) ──
    grading_template = {
        "instructions": (
            "Pour chaque question, lisez les 3 réponses (Système X, Y, Z) et "
            "attribuez un score de 0 à 5 pour chaque critère. "
            "Les systèmes sont anonymisés — vous ne savez pas lequel est lequel. "
            "Soyez aussi objectif que possible."
        ),
        "rubric": GRADING_RUBRIC,
        "evaluations": [],
    }

    for sheet in blind_sheets:
        eval_entry = {
            "question_id": sheet["question_id"],
            "chapter": sheet["chapter"],
            "mode": sheet["mode"],
            "question": sheet["question"],
            "grades": {},
        }
        for label in blind_labels:
            eval_entry["grades"][label] = {
                criterion: None for criterion in GRADING_RUBRIC
            }
            eval_entry["grades"][label]["comments"] = ""

        grading_template["evaluations"].append(eval_entry)

    # ── Guardrail evaluation (simple pass/fail) ──
    guardrail_sheet = {
        "instructions": (
            "Pour chaque question hors-programme, vérifiez si le système "
            "refuse correctement d'utiliser la méthode interdite. "
            "Score: PASS (refuse ou signale hors programme) / FAIL (utilise la méthode)."
        ),
        "evaluations": [],
    }

    for entry in guardrail_results:
        guard_entry = {
            "question_id": entry["question_id"],
            "question": entry["question"],
            "notes": entry["notes"],
            "systems": {},
        }
        for sys_name in system_names:
            sys_data = entry["systems"].get(sys_name, {})
            guard_entry["systems"][sys_name] = {
                "answer_preview": (sys_data.get("answer", ""))[:500],
                "verdict": None,  # Teacher fills: "PASS" or "FAIL"
                "comments": "",
            }
        guardrail_sheet["evaluations"].append(guard_entry)

    # ── Save everything ──
    output_dir = results_path.parent

    blind_path = output_dir / "blind_grading_sheet.json"
    with open(blind_path, "w", encoding="utf-8") as f:
        json.dump(blind_sheets, f, ensure_ascii=False, indent=2)
    print(f"  Blind grading sheet: {blind_path}")
    print(f"    ({len(blind_sheets)} questions × 3 anonymous systems)")

    key_path = output_dir / "answer_key.json"
    with open(key_path, "w", encoding="utf-8") as f:
        json.dump(answer_key, f, ensure_ascii=False, indent=2)
    print(f"  Answer key (SECRET): {key_path}")

    template_path = output_dir / "grading_template.json"
    with open(template_path, "w", encoding="utf-8") as f:
        json.dump(grading_template, f, ensure_ascii=False, indent=2)
    print(f"  Grading template:    {template_path}")
    print(f"    ({len(grading_template['evaluations'])} questions × 3 systems × 6 criteria)")

    guard_path = output_dir / "guardrail_evaluation.json"
    with open(guard_path, "w", encoding="utf-8") as f:
        json.dump(guardrail_sheet, f, ensure_ascii=False, indent=2)
    print(f"  Guardrail sheet:     {guard_path}")
    print(f"    ({len(guardrail_sheet['evaluations'])} out-of-scope questions × 3 systems)")

    print(f"\n  WORKFLOW:")
    print(f"    1. Send grading_template.json + blind_grading_sheet.json to your teachers")
    print(f"    2. Teachers fill in scores (0-5) for each criterion")
    print(f"    3. Teachers fill in guardrail_evaluation.json (PASS/FAIL)")
    print(f"    4. Run: python evaluation/analyze_grades.py")
    print(f"    5. Answer key reveals which system is which")


def main():
    parser = argparse.ArgumentParser(description="Generate blind grading sheets")
    parser.add_argument("--input", type=str,
                        default="evaluation/results/eval_results_latest.json",
                        help="Path to evaluation results JSON")
    args = parser.parse_args()

    results_path = Path(args.input)
    if not results_path.is_absolute():
        results_path = PROJECT_ROOT / results_path

    if not results_path.exists():
        print(f"Results file not found: {results_path}")
        print(f"Run evaluation first: python evaluation/run_evaluation.py")
        sys.exit(1)

    print(f"Generating grading sheets from: {results_path}\n")
    generate_sheets(results_path)


if __name__ == "__main__":
    main()
