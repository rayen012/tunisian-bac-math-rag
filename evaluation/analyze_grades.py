#!/usr/bin/env python3
"""
analyze_grades.py
-----------------
After your teachers have filled in the grading_template.json, run this script
to unblind the results and produce thesis-ready analysis.

Outputs:
  - Per-system average scores across all 6 criteria
  - Per-category breakdown (A vs B vs C vs D)
  - Per-criterion comparison table (LaTeX-ready)
  - Guardrail pass/fail summary
  - Statistical significance notes

Usage:
  python evaluation/analyze_grades.py
  python evaluation/analyze_grades.py --grades evaluation/results/grading_template_filled.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Criterion weights (same as in generate_grading_sheets.py)
WEIGHTS = {
    "mathematical_correctness": 5,
    "formal_rigor": 5,
    "bac_style_alignment": 3,
    "clarity_and_structure": 3,
    "pedagogical_quality": 2,
    "hallucination_penalty": 2,
}
TOTAL_WEIGHT = sum(WEIGHTS.values())  # = 20


def load_and_unblind(grades_path: Path, key_path: Path):
    """Load filled grades and unblind using the answer key."""
    with open(grades_path, "r", encoding="utf-8") as f:
        grades_data = json.load(f)
    with open(key_path, "r", encoding="utf-8") as f:
        answer_key = json.load(f)

    # Build lookup: question_id → {blind_label → real_system}
    key_lookup = {}
    for entry in answer_key:
        qid = entry["question_id"]
        key_lookup[qid] = {
            "Système X": entry["Système X"],
            "Système Y": entry["Système Y"],
            "Système Z": entry["Système Z"],
        }

    # Unblind: attach real system names to each grade
    unblinded = []
    for eval_entry in grades_data["evaluations"]:
        qid = eval_entry["question_id"]
        mapping = key_lookup.get(qid, {})

        for blind_label, scores in eval_entry["grades"].items():
            real_system = mapping.get(blind_label, "UNKNOWN")
            unblinded.append({
                "question_id": qid,
                "chapter": eval_entry.get("chapter", ""),
                "mode": eval_entry.get("mode", ""),
                "system": real_system,
                "scores": {k: v for k, v in scores.items() if k != "comments"},
                "comments": scores.get("comments", ""),
            })

    return unblinded


def compute_weighted_score(scores: dict) -> float:
    """Compute weighted total score (out of 20) from individual criterion scores."""
    total = 0
    for criterion, weight in WEIGHTS.items():
        raw = scores.get(criterion)
        if raw is not None:
            # Each criterion is scored 0-5, weight determines how much of /20 it gets
            total += (raw / 5.0) * weight
    return round(total, 2)


def analyze(unblinded: list):
    """Produce all analysis tables."""
    # ── Per-system averages ──
    system_scores = defaultdict(lambda: defaultdict(list))
    system_totals = defaultdict(list)

    for entry in unblinded:
        sys_name = entry["system"]
        for criterion, score in entry["scores"].items():
            if score is not None:
                system_scores[sys_name][criterion].append(score)
        weighted = compute_weighted_score(entry["scores"])
        system_totals[sys_name].append(weighted)

    print("\n" + "=" * 70)
    print("  UNBLINDED RESULTS — Per-System Average Scores")
    print("=" * 70)

    # Header
    systems = ["RAG", "PROMPT_ONLY", "HYBRID"]
    header = f"  {'Criterion':<30s}"
    for s in systems:
        header += f"  {s:>12s}"
    print(header)
    print("  " + "─" * 66)

    for criterion in WEIGHTS:
        row = f"  {criterion:<30s}"
        for s in systems:
            vals = system_scores[s][criterion]
            if vals:
                avg = sum(vals) / len(vals)
                row += f"  {avg:>10.2f}/5"
            else:
                row += f"  {'N/A':>12s}"
        print(row)

    print("  " + "─" * 66)
    row = f"  {'WEIGHTED TOTAL (/20)':<30s}"
    for s in systems:
        vals = system_totals[s]
        if vals:
            avg = sum(vals) / len(vals)
            row += f"  {avg:>11.2f}/20"
        else:
            row += f"  {'N/A':>12s}"
    print(row)

    # ── Per-category breakdown ──
    print("\n\n" + "=" * 70)
    print("  Per-Category Weighted Scores (/20)")
    print("=" * 70)

    from evaluation.eval_questions import EVAL_QUESTIONS
    qid_to_cat = {q["id"]: q["category"] for q in EVAL_QUESTIONS}

    cat_scores = defaultdict(lambda: defaultdict(list))
    for entry in unblinded:
        cat = qid_to_cat.get(entry["question_id"], "?")
        weighted = compute_weighted_score(entry["scores"])
        cat_scores[cat][entry["system"]].append(weighted)

    cat_labels = {
        "A": "Direct Bac-style",
        "B": "Novel chapter-based",
        "C": "Student informal",
        "D": "Derja / mixed",
    }
    header = f"  {'Category':<25s}"
    for s in systems:
        header += f"  {s:>12s}"
    print(header)
    print("  " + "─" * 61)

    for cat in "ABCD":
        label = cat_labels.get(cat, cat)
        row = f"  {cat}: {label:<20s}"
        for s in systems:
            vals = cat_scores[cat][s]
            if vals:
                avg = sum(vals) / len(vals)
                row += f"  {avg:>11.2f}/20"
            else:
                row += f"  {'N/A':>12s}"
        print(row)

    # ── LaTeX table ──
    print("\n\n" + "=" * 70)
    print("  LaTeX-ready comparison table (copy into thesis)")
    print("=" * 70)
    print(r"""
\begin{table}[H]
\centering
\caption{Human evaluation results: average scores per criterion (0--5 scale) and
weighted total (/20). Scores are averaged across all graded questions (categories A--D).
Higher is better for all criteria.}
\label{tab:human-evaluation}
\begin{tabular}{lrrr}
\toprule
\textbf{Criterion} & \textbf{RAG} & \textbf{Prompt-Only} & \textbf{Hybrid} \\
\midrule""")

    for criterion, weight in WEIGHTS.items():
        label = criterion.replace("_", " ").title()
        vals = []
        for s in systems:
            v = system_scores[s][criterion]
            vals.append(f"{sum(v)/len(v):.2f}" if v else "N/A")
        print(f"{label} (w={weight}) & {vals[0]} & {vals[1]} & {vals[2]} \\\\")

    print(r"\midrule")
    totals = []
    for s in systems:
        v = system_totals[s]
        totals.append(f"{sum(v)/len(v):.2f}" if v else "N/A")
    print(f"\\textbf{{Weighted Total (/20)}} & \\textbf{{{totals[0]}}} & "
          f"\\textbf{{{totals[1]}}} & \\textbf{{{totals[2]}}} \\\\")
    print(r"""\bottomrule
\end{tabular}
\end{table}""")


def analyze_guardrails(guard_path: Path):
    """Analyze guardrail pass/fail results."""
    if not guard_path.exists():
        print(f"\n  Guardrail file not found: {guard_path}")
        return

    with open(guard_path, "r", encoding="utf-8") as f:
        guard_data = json.load(f)

    print("\n\n" + "=" * 70)
    print("  GUARDRAIL RESULTS (Out-of-Scope Questions)")
    print("=" * 70)

    systems = ["RAG", "PROMPT_ONLY", "HYBRID"]
    pass_counts = defaultdict(int)
    total = len(guard_data["evaluations"])

    for entry in guard_data["evaluations"]:
        print(f"\n  {entry['question_id']}: {entry['question'][:60]}...")
        for sys_name in systems:
            verdict = entry["systems"][sys_name].get("verdict", "NOT_GRADED")
            symbol = "PASS" if verdict == "PASS" else ("FAIL" if verdict == "FAIL" else "?")
            print(f"    {sys_name:<15s}: {symbol}")
            if verdict == "PASS":
                pass_counts[sys_name] += 1

    print(f"\n  Summary:")
    for s in systems:
        print(f"    {s:<15s}: {pass_counts[s]}/{total} passed")


def main():
    parser = argparse.ArgumentParser(description="Analyze teacher grades")
    parser.add_argument("--grades", type=str,
                        default="evaluation/results/grading_template.json",
                        help="Path to filled grading template")
    parser.add_argument("--key", type=str,
                        default="evaluation/results/answer_key.json",
                        help="Path to answer key")
    parser.add_argument("--guardrails", type=str,
                        default="evaluation/results/guardrail_evaluation.json",
                        help="Path to guardrail evaluation")
    args = parser.parse_args()

    grades_path = Path(args.grades)
    key_path = Path(args.key)
    guard_path = Path(args.guardrails)

    if not grades_path.is_absolute():
        grades_path = PROJECT_ROOT / grades_path
    if not key_path.is_absolute():
        key_path = PROJECT_ROOT / key_path
    if not guard_path.is_absolute():
        guard_path = PROJECT_ROOT / guard_path

    if not grades_path.exists():
        print(f"Grading template not found: {grades_path}")
        print("Ask your teachers to fill in the template first.")
        sys.exit(1)
    if not key_path.exists():
        print(f"Answer key not found: {key_path}")
        sys.exit(1)

    unblinded = load_and_unblind(grades_path, key_path)
    analyze(unblinded)
    analyze_guardrails(guard_path)


if __name__ == "__main__":
    main()
