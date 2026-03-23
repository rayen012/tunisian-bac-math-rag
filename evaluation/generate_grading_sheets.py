#!/usr/bin/env python3
"""
generate_grading_sheets.py
--------------------------
Takes evaluation results JSON and produces:
  1. blind_grading_sheet.json  — Anonymized answers (Système X/Y/Z) for teachers
  2. answer_key.json           — Reveals which system is which (keep SECRET)
  3. grading_template.json     — Pre-filled template with empty scores for teachers
  4. guardrail_evaluation.json — Blind pass/fail for out-of-scope questions

All outputs are fully blind: teachers never see system names (RAG, Prompt-Only,
Hybrid). The answer key maps Système X/Y/Z back to real names for analysis.

Grading rubric: 4 criteria, each scored 0–5, equally weighted.
  1. mathematical_correctness
  2. reasoning_clarity
  3. pedagogical_quality
  4. bac_style_adherence

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

# ── Grading rubric — 4 criteria, each scored 0-5, equally weighted ──────────
GRADING_RUBRIC = {
    "mathematical_correctness": {
        "description": (
            "Les calculs et raisonnements mathématiques sont-ils corrects ? "
            "(0 = tout faux ou absurde, 5 = parfaitement correct)"
        ),
        "scale": "0-5",
    },
    "reasoning_clarity": {
        "description": (
            "Le raisonnement est-il clair, logique et bien structuré ? "
            "Les étapes sont-elles faciles à suivre ? "
            "(0 = incompréhensible, 5 = parfaitement clair et ordonné)"
        ),
        "scale": "0-5",
    },
    "pedagogical_quality": {
        "description": (
            "La réponse aide-t-elle l'élève à comprendre la méthode, "
            "pas seulement à obtenir le résultat ? "
            "(0 = aucune valeur pédagogique, 5 = excellent support d'apprentissage)"
        ),
        "scale": "0-5",
    },
    "bac_style_adherence": {
        "description": (
            "La réponse ressemble-t-elle à une correction officielle du Bac tunisien ? "
            "Utilise-t-elle les conventions formelles (« On a… », « Donc… », « D'après… »), "
            "la rédaction académique en français, et le niveau de détail attendu ? "
            "(0 = pas du tout, 5 = indistinguable d'une correction officielle)"
        ),
        "scale": "0-5",
    },
}

CRITERIA = list(GRADING_RUBRIC.keys())
BLIND_LABELS = ["Système X", "Système Y", "Système Z"]
SYSTEM_NAMES = ["RAG", "PROMPT_ONLY", "HYBRID"]


def _shuffle_systems(rng: random.Random) -> list:
    """Return a shuffled copy of SYSTEM_NAMES using the given RNG."""
    shuffled = list(SYSTEM_NAMES)
    rng.shuffle(shuffled)
    return shuffled


def generate_sheets(results_path: Path):
    """Generate blind grading sheets from evaluation results."""
    with open(results_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data["results"]

    # Separate main questions (A-D) from guardrail questions (E)
    graded_results = [r for r in results if r["category"] != "E"]
    guardrail_results = [r for r in results if r["category"] == "E"]

    rng = random.Random(42)  # Reproducible shuffling

    blind_sheets = []
    answer_key = []

    # ── Main questions (categories A-D): blind 4-criterion grading ───────
    for entry in graded_results:
        shuffled = _shuffle_systems(rng)

        sheet = {
            "question_id": entry["question_id"],
            "category": entry["category"],
            "chapter": entry["chapter"],
            "mode": entry["mode"],
            "question": entry["question"],
            "answers": {},
        }

        for label, sys_name in zip(BLIND_LABELS, shuffled):
            sys_data = entry["systems"].get(sys_name, {})
            sheet["answers"][label] = sys_data.get("answer", "[ERREUR: pas de réponse]")

        blind_sheets.append(sheet)

        answer_key.append({
            "question_id": entry["question_id"],
            "category": entry["category"],
            "Système X": shuffled[0],
            "Système Y": shuffled[1],
            "Système Z": shuffled[2],
        })

    # ── Guardrail questions (category E): blind pass/fail ────────────────
    guardrail_sheets = []

    for entry in guardrail_results:
        shuffled = _shuffle_systems(rng)

        guard_sheet = {
            "question_id": entry["question_id"],
            "question": entry["question"],
            "notes": entry["notes"],
            "answers": {},
        }

        for label, sys_name in zip(BLIND_LABELS, shuffled):
            sys_data = entry["systems"].get(sys_name, {})
            guard_sheet["answers"][label] = {
                "answer": sys_data.get("answer", "[ERREUR: pas de réponse]"),
                "verdict": None,  # Teacher fills: "PASS" or "FAIL"
                "comments": "",
            }

        guardrail_sheets.append(guard_sheet)

        answer_key.append({
            "question_id": entry["question_id"],
            "category": "E",
            "Système X": shuffled[0],
            "Système Y": shuffled[1],
            "Système Z": shuffled[2],
        })

    # ── Grading template (what the teacher fills in) ─────────────────────
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
        for label in BLIND_LABELS:
            eval_entry["grades"][label] = {
                criterion: None for criterion in CRITERIA
            }
            eval_entry["grades"][label]["comments"] = ""

        grading_template["evaluations"].append(eval_entry)

    # ── Guardrail template ───────────────────────────────────────────────
    guardrail_template = {
        "instructions": (
            "Pour chaque question hors-programme ci-dessous, lisez les 3 réponses "
            "(Système X, Y, Z) et indiquez si le système refuse correctement "
            "d'utiliser la méthode interdite.\n"
            "Verdict : PASS (refuse ou signale explicitement que c'est hors programme) "
            "/ FAIL (utilise la méthode interdite sans avertir)."
        ),
        "evaluations": guardrail_sheets,
    }

    # ── Save everything ──────────────────────────────────────────────────
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
    print(f"    (covers {len(graded_results)} graded + {len(guardrail_results)} guardrail questions)")

    template_path = output_dir / "grading_template.json"
    with open(template_path, "w", encoding="utf-8") as f:
        json.dump(grading_template, f, ensure_ascii=False, indent=2)
    print(f"  Grading template:    {template_path}")
    print(f"    ({len(grading_template['evaluations'])} questions × 3 systems × {len(CRITERIA)} criteria)")

    guard_path = output_dir / "guardrail_evaluation.json"
    with open(guard_path, "w", encoding="utf-8") as f:
        json.dump(guardrail_template, f, ensure_ascii=False, indent=2)
    print(f"  Guardrail sheet:     {guard_path}")
    print(f"    ({len(guardrail_sheets)} out-of-scope questions × 3 blind systems, full answers)")

    print(f"\n  WORKFLOW:")
    print(f"    1. Send grading_template.json + blind_grading_sheet.json to your teacher")
    print(f"    2. Send guardrail_evaluation.json separately (PASS/FAIL only)")
    print(f"    3. Teacher fills in scores (0-5) and verdicts")
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
