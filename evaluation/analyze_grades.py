#!/usr/bin/env python3
"""
Unblinds teacher grades and computes per-system/per-category averages.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# The 4 evaluation criteria (must match generate_grading_sheets.py)
CRITERIA = [
    "mathematical_correctness",
    "reasoning_clarity",
    "pedagogical_quality",
    "bac_style_adherence",
]

CRITERIA_LABELS = {
    "mathematical_correctness": "Mathematical Correctness",
    "reasoning_clarity": "Reasoning Clarity",
    "pedagogical_quality": "Pedagogical Quality",
    "bac_style_adherence": "Bac Style Adherence",
}

SYSTEMS = ["RAG", "PROMPT_ONLY", "HYBRID"]


def load_answer_key(key_path: Path) -> dict:
    """Load answer key and build lookup: question_id → {blind_label → real_system}."""
    with open(key_path, "r", encoding="utf-8") as f:
        answer_key = json.load(f)

    lookup = {}
    for entry in answer_key:
        qid = entry["question_id"]
        lookup[qid] = {
            "Système X": entry["Système X"],
            "Système Y": entry["Système Y"],
            "Système Z": entry["Système Z"],
            "category": entry.get("category", ""),
        }
    return lookup


def load_and_unblind_grades(grades_path: Path, key_lookup: dict) -> list:
    """Load filled grades and unblind using the answer key."""
    with open(grades_path, "r", encoding="utf-8") as f:
        grades_data = json.load(f)

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


def compute_mean(scores: dict) -> float:
    """Compute simple (unweighted) mean of scored criteria, out of 5."""
    values = [v for k, v in scores.items() if k in CRITERIA and v is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def analyze(unblinded: list):
    """Produce all analysis tables from unblinded grades."""
    system_scores = defaultdict(lambda: defaultdict(list))
    system_means = defaultdict(list)

    for entry in unblinded:
        sys_name = entry["system"]
        for criterion in CRITERIA:
            score = entry["scores"].get(criterion)
            if score is not None:
                system_scores[sys_name][criterion].append(score)
        mean = compute_mean(entry["scores"])
        system_means[sys_name].append(mean)

    # ── Per-system per-criterion averages ──
    print("\n" + "=" * 70)
    print("  UNBLINDED RESULTS — Per-System Average Scores (0-5)")
    print("=" * 70)

    header = f"  {'Criterion':<30s}"
    for s in SYSTEMS:
        header += f"  {s:>12s}"
    print(header)
    print("  " + "─" * 66)

    for criterion in CRITERIA:
        row = f"  {CRITERIA_LABELS[criterion]:<30s}"
        for s in SYSTEMS:
            vals = system_scores[s][criterion]
            if vals:
                avg = sum(vals) / len(vals)
                row += f"  {avg:>10.2f}/5"
            else:
                row += f"  {'N/A':>12s}"
        print(row)

    print("  " + "─" * 66)
    row = f"  {'MEAN (unweighted)':<30s}"
    for s in SYSTEMS:
        vals = system_means[s]
        if vals:
            avg = sum(vals) / len(vals)
            row += f"  {avg:>10.2f}/5"
        else:
            row += f"  {'N/A':>12s}"
    print(row)

    n_questions = len(system_means[SYSTEMS[0]]) if system_means[SYSTEMS[0]] else 0
    print(f"\n  Based on {n_questions} graded questions (categories A-D).")

    # ── Per-category breakdown ──
    print("\n\n" + "=" * 70)
    print("  Per-Category Mean Scores (0-5, unweighted)")
    print("=" * 70)

    from evaluation.eval_questions import EVAL_QUESTIONS
    qid_to_cat = {q["id"]: q["category"] for q in EVAL_QUESTIONS}

    cat_means = defaultdict(lambda: defaultdict(list))
    for entry in unblinded:
        cat = qid_to_cat.get(entry["question_id"], "?")
        mean = compute_mean(entry["scores"])
        cat_means[cat][entry["system"]].append(mean)

    cat_labels = {
        "A": "Direct Bac-style",
        "B": "Novel chapter-based",
        "C": "Student informal",
        "D": "Derja / mixed",
    }
    header = f"  {'Category':<25s}"
    for s in SYSTEMS:
        header += f"  {s:>12s}"
    print(header)
    print("  " + "─" * 61)

    for cat in "ABCD":
        label = cat_labels.get(cat, cat)
        row = f"  {cat}: {label:<20s}"
        for s in SYSTEMS:
            vals = cat_means[cat][s]
            if vals:
                avg = sum(vals) / len(vals)
                row += f"  {avg:>10.2f}/5"
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
\caption{Human evaluation results: average scores per criterion (0--5 scale)
and unweighted mean, as assessed by a Tunisian Baccalaureate mathematics teacher
through blind grading of system outputs (categories A--D).
Higher is better for all criteria.}
\label{tab:human-evaluation}
\begin{tabular}{lrrr}
\toprule
\textbf{Criterion} & \textbf{RAG} & \textbf{Prompt-Only} & \textbf{Hybrid} \\
\midrule""")

    for criterion in CRITERIA:
        label = CRITERIA_LABELS[criterion]
        vals = []
        for s in SYSTEMS:
            v = system_scores[s][criterion]
            vals.append(f"{sum(v)/len(v):.2f}" if v else "N/A")
        print(f"{label} & {vals[0]} & {vals[1]} & {vals[2]} \\\\")

    print(r"\midrule")
    vals = []
    for s in SYSTEMS:
        v = system_means[s]
        vals.append(f"{sum(v)/len(v):.2f}" if v else "N/A")
    print(f"\\textbf{{Mean}} & \\textbf{{{vals[0]}}} & "
          f"\\textbf{{{vals[1]}}} & \\textbf{{{vals[2]}}} \\\\")
    print(r"""\bottomrule
\end{tabular}
\end{table}""")


def analyze_guardrails(guard_path: Path, key_lookup: dict):
    """Analyze guardrail pass/fail results, unblinding from the answer key."""
    if not guard_path.exists():
        print(f"\n  Guardrail file not found: {guard_path}")
        return

    with open(guard_path, "r", encoding="utf-8") as f:
        guard_data = json.load(f)

    print("\n\n" + "=" * 70)
    print("  GUARDRAIL RESULTS (Out-of-Scope Questions) — Unblinded")
    print("=" * 70)

    pass_counts = defaultdict(int)
    total = len(guard_data["evaluations"])
    blind_labels = ["Système X", "Système Y", "Système Z"]

    for entry in guard_data["evaluations"]:
        qid = entry["question_id"]
        mapping = key_lookup.get(qid, {})

        print(f"\n  {qid}: {entry['question'][:70]}...")
        for label in blind_labels:
            real_system = mapping.get(label, "UNKNOWN")
            answer_data = entry["answers"].get(label, {})
            verdict = answer_data.get("verdict", "NOT_GRADED")
            symbol = "PASS" if verdict == "PASS" else ("FAIL" if verdict == "FAIL" else "?")
            print(f"    {label} ({real_system:<12s}): {symbol}")
            if verdict == "PASS":
                pass_counts[real_system] += 1

    print(f"\n  Summary:")
    for s in SYSTEMS:
        print(f"    {s:<15s}: {pass_counts[s]}/{total} passed")

    # LaTeX guardrail table
    print(f"\n  LaTeX guardrail table:")
    print(r"""
\begin{table}[H]
\centering
\caption{Curriculum guardrail results: number of out-of-scope questions
correctly refused (out of """ + str(total) + r""").}
\label{tab:guardrail-results}
\begin{tabular}{lr}
\toprule
\textbf{System} & \textbf{Pass Rate} \\
\midrule""")
    for s in SYSTEMS:
        display = s.replace("_", "-").title().replace("Prompt-Only", "Prompt-Only")
        if s == "PROMPT_ONLY":
            display = "Prompt-Only"
        elif s == "RAG":
            display = "RAG"
        elif s == "HYBRID":
            display = "Hybrid"
        print(f"{display} & {pass_counts[s]}/{total} \\\\")
    print(r"""\bottomrule
\end{tabular}
\end{table}""")


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
        print("Ask your teacher to fill in the template first.")
        sys.exit(1)
    if not key_path.exists():
        print(f"Answer key not found: {key_path}")
        sys.exit(1)

    key_lookup = load_answer_key(key_path)
    unblinded = load_and_unblind_grades(grades_path, key_lookup)
    analyze(unblinded)
    analyze_guardrails(guard_path, key_lookup)


if __name__ == "__main__":
    main()
