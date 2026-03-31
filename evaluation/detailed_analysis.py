#!/usr/bin/env python3
"""
Post-evaluation analysis: per-question breakdown, case distribution, retrieval
quality, and qualitative examples for the thesis.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from evaluation.eval_questions import EVAL_QUESTIONS

SYSTEMS = ["RAG", "PROMPT_ONLY", "HYBRID"]
CRITERIA = [
    "mathematical_correctness",
    "reasoning_clarity",
    "pedagogical_quality",
    "bac_style_adherence",
]
CRITERIA_SHORT = {
    "mathematical_correctness": "Math",
    "reasoning_clarity": "Clarity",
    "pedagogical_quality": "Pedagogy",
    "bac_style_adherence": "Bac Style",
}


# ═════════════════════════════════════════════════════════════════════════════
#  1. PER-QUESTION DETAILED BREAKDOWN
# ═════════════════════════════════════════════════════════════════════════════

def per_question_breakdown(eval_data: dict, grades_data: dict = None,
                           key_lookup: dict = None):
    """
    Produce a per-question × per-system × per-criterion matrix.

    If teacher grades are available, merges them. Otherwise uses system metadata
    (retrieval case, distance, timing) for the breakdown.
    """
    results = eval_data["results"]

    print(f"\n{'=' * 70}")
    print("  1. PER-QUESTION DETAILED BREAKDOWN")
    print(f"{'=' * 70}")

    # ── Table: System metadata per question ──
    print(f"\n  {'ID':<5s} {'Cat':<4s} {'Chapter':<22s} "
          f"{'RAG case':>8s} {'RAG dist':>9s} {'HYB case':>9s} {'HYB dist':>9s}")
    print(f"  {'─' * 76}")

    breakdown = []
    for entry in results:
        qid = entry["question_id"]
        cat = entry["category"]
        chapter = entry["chapter"][:20]

        rag = entry["systems"].get("RAG", {})
        hyb = entry["systems"].get("HYBRID", {})

        rag_case = rag.get("retrieval_case", "—")
        rag_dist = rag.get("best_distance")
        hyb_case = hyb.get("retrieval_case", "—")
        hyb_dist = hyb.get("best_distance")

        rag_dist_str = f"{rag_dist:.4f}" if rag_dist is not None else "—"
        hyb_dist_str = f"{hyb_dist:.4f}" if hyb_dist is not None else "—"

        print(f"  {qid:<5s} {cat:<4s} {chapter:<22s} "
              f"{rag_case:>8s} {rag_dist_str:>9s} {hyb_case:>9s} {hyb_dist_str:>9s}")

        row = {
            "question_id": qid,
            "category": cat,
            "chapter": entry["chapter"],
            "mode": entry["mode"],
            "rag_case": rag_case,
            "rag_best_distance": rag_dist,
            "hybrid_case": hyb_case,
            "hybrid_best_distance": hyb_dist,
            "rag_n_docs": rag.get("n_selected_docs", 0),
            "hybrid_n_docs": hyb.get("n_selected_docs", 0),
            "rag_answer_length": rag.get("answer_length", 0),
            "po_answer_length": entry["systems"].get("PROMPT_ONLY", {}).get("answer_length", 0),
            "hybrid_answer_length": hyb.get("answer_length", 0),
        }

        # If teacher grades available, add them
        if grades_data and key_lookup:
            row["grades"] = _get_grades_for_question(qid, grades_data, key_lookup)

        breakdown.append(row)

    # ── If grades available, print the full heatmap ──
    if grades_data and key_lookup:
        _print_grade_heatmap(breakdown)

    return breakdown


def _get_grades_for_question(qid: str, grades_data: dict, key_lookup: dict) -> dict:
    """Extract per-system grades for a single question."""
    mapping = key_lookup.get(qid, {})
    grades = {}

    for eval_entry in grades_data.get("evaluations", []):
        if eval_entry["question_id"] != qid:
            continue
        for blind_label, scores in eval_entry.get("grades", {}).items():
            real_system = mapping.get(blind_label, "UNKNOWN")
            grades[real_system] = {
                k: v for k, v in scores.items() if k in CRITERIA
            }
    return grades


def _print_grade_heatmap(breakdown: list):
    """Print per-question × per-system grade matrix."""
    print(f"\n\n  Per-Question Grade Matrix (0-5 scale):")
    print(f"  {'ID':<5s} {'Cat':<4s} ", end="")
    for sys_name in SYSTEMS:
        short = sys_name[:3] if sys_name != "PROMPT_ONLY" else "P-O"
        for c in CRITERIA_SHORT.values():
            print(f" {short}:{c:>4s}", end="")
    print()
    print(f"  {'─' * 100}")

    for row in breakdown:
        if "grades" not in row or not row["grades"]:
            continue
        print(f"  {row['question_id']:<5s} {row['category']:<4s} ", end="")
        for sys_name in SYSTEMS:
            sys_grades = row["grades"].get(sys_name, {})
            for crit in CRITERIA:
                score = sys_grades.get(crit)
                if score is not None:
                    print(f" {score:>8.0f}", end="")
                else:
                    print(f" {'—':>8s}", end="")
        print()


# ═════════════════════════════════════════════════════════════════════════════
#  2. RETRIEVAL CASE (A/B/C) DISTRIBUTION & ROUTING ANALYSIS
# ═════════════════════════════════════════════════════════════════════════════

def case_distribution_analysis(eval_data: dict):
    """Analyze how queries distribute across routing cases A, B, C."""
    results = eval_data["results"]

    print(f"\n\n{'=' * 70}")
    print("  2. RETRIEVAL CASE (A/B/C) DISTRIBUTION")
    print(f"{'=' * 70}")

    # Count cases for RAG and Hybrid
    rag_cases = defaultdict(list)
    hybrid_cases = defaultdict(list)

    for entry in results:
        qid = entry["question_id"]
        cat = entry["category"]

        rag = entry["systems"].get("RAG", {})
        hyb = entry["systems"].get("HYBRID", {})

        rag_case = rag.get("retrieval_case", "UNKNOWN")
        hyb_case = hyb.get("retrieval_case", "UNKNOWN")

        rag_cases[rag_case].append({"qid": qid, "cat": cat,
                                     "dist": rag.get("best_distance")})
        hybrid_cases[hyb_case].append({"qid": qid, "cat": cat,
                                        "dist": hyb.get("best_distance")})

    # Print distribution
    n = len(results)
    print(f"\n  RAG Engine Case Distribution ({n} queries):")
    for case in ["A", "B", "C", "UNKNOWN"]:
        if rag_cases[case]:
            pct = len(rag_cases[case]) / n * 100
            qids = [r["qid"] for r in rag_cases[case]]
            print(f"    Case {case}: {len(rag_cases[case]):>2d}/{n} ({pct:.0f}%) — {', '.join(qids)}")

    print(f"\n  Hybrid Engine Case Distribution ({n} queries):")
    for case in ["A", "B", "C", "UNKNOWN"]:
        if hybrid_cases[case]:
            pct = len(hybrid_cases[case]) / n * 100
            qids = [r["qid"] for r in hybrid_cases[case]]
            print(f"    Case {case}: {len(hybrid_cases[case]):>2d}/{n} ({pct:.0f}%) — {', '.join(qids)}")

    # Per-category case breakdown
    print(f"\n  Per-Category Routing (Hybrid Engine):")
    for cat in "ABCDE":
        cat_entries = [e for e in results if e["category"] == cat]
        if not cat_entries:
            continue
        case_counts = defaultdict(int)
        for e in cat_entries:
            case = e["systems"].get("HYBRID", {}).get("retrieval_case", "?")
            case_counts[case] += 1
        parts = [f"Case {c}={n}" for c, n in sorted(case_counts.items())]
        print(f"    Category {cat}: {', '.join(parts)}")

    # First-pass vs second-pass analysis
    print(f"\n  First-Pass vs Second-Pass Retrieval:")
    for entry in results:
        if entry["category"] == "E":
            continue  # Skip guardrail questions
        rag = entry["systems"].get("RAG", {})
        n_first = rag.get("n_first_pass_docs", 0)
        n_second = rag.get("n_second_pass_docs", 0)
        case = rag.get("retrieval_case", "?")
        print(f"    {entry['question_id']} (case {case}): "
              f"first_pass={n_first}, second_pass={n_second}, "
              f"total_selected={rag.get('n_selected_docs', 0)}")

    return {
        "rag_cases": {k: len(v) for k, v in rag_cases.items()},
        "hybrid_cases": {k: len(v) for k, v in hybrid_cases.items()},
    }


# ═════════════════════════════════════════════════════════════════════════════
#  3. RETRIEVAL QUALITY METRICS
# ═════════════════════════════════════════════════════════════════════════════

def retrieval_quality_analysis(eval_data: dict):
    """Analyze L2 distance distributions, retrieved document types, chapters."""
    results = eval_data["results"]

    print(f"\n\n{'=' * 70}")
    print("  3. RETRIEVAL QUALITY / DISTANCE ANALYSIS")
    print(f"{'=' * 70}")

    # Collect distances
    rag_distances = []
    hybrid_distances = []
    per_question = []

    for entry in results:
        rag = entry["systems"].get("RAG", {})
        hyb = entry["systems"].get("HYBRID", {})

        rag_dist = rag.get("best_distance")
        hyb_dist = hyb.get("best_distance")

        if rag_dist is not None:
            rag_distances.append(rag_dist)
        if hyb_dist is not None:
            hybrid_distances.append(hyb_dist)

        # Analyze retrieved sources
        rag_sources = rag.get("retrieved_sources", [])
        chapters_retrieved = set()
        types_retrieved = defaultdict(int)
        for src in rag_sources:
            if src.get("chapter"):
                chapters_retrieved.add(src["chapter"])
            if src.get("type"):
                types_retrieved[src["type"]] += 1

        per_question.append({
            "qid": entry["question_id"],
            "category": entry["category"],
            "expected_chapter": entry["chapter"],
            "rag_best_dist": rag_dist,
            "hybrid_best_dist": hyb_dist,
            "n_rag_sources": len(rag_sources),
            "chapters_retrieved": list(chapters_retrieved),
            "chapter_match": entry["chapter"] in chapters_retrieved,
            "types_retrieved": dict(types_retrieved),
        })

    # Distance statistics
    if rag_distances:
        print(f"\n  RAG Best Distance Distribution ({len(rag_distances)} queries):")
        print(f"    Mean:   {np.mean(rag_distances):.4f}")
        print(f"    Median: {np.median(rag_distances):.4f}")
        print(f"    Min:    {np.min(rag_distances):.4f}")
        print(f"    Max:    {np.max(rag_distances):.4f}")
        print(f"    Std:    {np.std(rag_distances):.4f}")
        # Histogram buckets
        bins = [0, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0, 999]
        labels = ["<0.8", "0.8-1.0", "1.0-1.2", "1.2-1.4", "1.4-1.6", "1.6-2.0", ">2.0"]
        counts, _ = np.histogram(rag_distances, bins=bins)
        print(f"\n    Distance histogram:")
        for label, count in zip(labels, counts):
            bar = "█" * count
            print(f"      {label:>7s}: {count:>2d} {bar}")

    # Chapter match analysis
    n_match = sum(1 for pq in per_question if pq["chapter_match"])
    n_total = sum(1 for pq in per_question if pq["n_rag_sources"] > 0)
    print(f"\n  Chapter Match Analysis:")
    print(f"    Queries with correct chapter in retrieved docs: {n_match}/{n_total}")
    for pq in per_question:
        match_str = "MATCH" if pq["chapter_match"] else "MISS"
        print(f"    {pq['qid']} ({pq['category']}): expected={pq['expected_chapter']}, "
              f"got={pq['chapters_retrieved'][:3]} [{match_str}]")

    # Document type breakdown
    print(f"\n  Retrieved Document Types (across all queries):")
    all_types = defaultdict(int)
    for pq in per_question:
        for t, c in pq["types_retrieved"].items():
            all_types[t] += c
    for t, c in sorted(all_types.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    return {
        "rag_distance_stats": {
            "mean": round(float(np.mean(rag_distances)), 4) if rag_distances else None,
            "median": round(float(np.median(rag_distances)), 4) if rag_distances else None,
            "std": round(float(np.std(rag_distances)), 4) if rag_distances else None,
        },
        "chapter_match_rate": n_match / n_total if n_total > 0 else 0,
        "per_question": per_question,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  4. QUALITATIVE EXAMPLES
# ═════════════════════════════════════════════════════════════════════════════

def qualitative_examples(eval_data: dict, show_full: bool = False):
    """Extract representative examples for side-by-side comparison in thesis.

    Selects:
      - One question where Prompt-Only clearly dominates
      - One question where RAG/Hybrid is closest to Prompt-Only
      - One Derja question (if available)
    """
    results = eval_data["results"]

    print(f"\n\n{'=' * 70}")
    print("  4. QUALITATIVE EXAMPLES (Side-by-Side)")
    print(f"{'=' * 70}")

    # Strategy: select examples by answer length ratio and retrieval case
    examples = []

    for entry in results:
        if entry["category"] == "E":
            continue

        rag = entry["systems"].get("RAG", {})
        po = entry["systems"].get("PROMPT_ONLY", {})
        hyb = entry["systems"].get("HYBRID", {})

        examples.append({
            "qid": entry["question_id"],
            "category": entry["category"],
            "chapter": entry["chapter"],
            "mode": entry["mode"],
            "question": entry["question"],
            "rag_case": rag.get("retrieval_case", "?"),
            "rag_dist": rag.get("best_distance"),
            "rag_answer": rag.get("answer", ""),
            "po_answer": po.get("answer", ""),
            "hybrid_answer": hyb.get("answer", ""),
            "hybrid_case": hyb.get("retrieval_case", "?"),
            "rag_confidence": rag.get("confidence", "?"),
            "po_confidence": po.get("confidence", "?"),
            "hybrid_confidence": hyb.get("confidence", "?"),
            "hybrid_source": hyb.get("knowledge_source", "?"),
            "rag_time": rag.get("total_time_s", 0),
            "po_time": po.get("total_time_s", 0),
            "hybrid_time": hyb.get("total_time_s", 0),
        })

    if not examples:
        print("  No graded examples found.")
        return []

    # ── Select representative examples ──
    selected = []

    # Example 1: Best RAG case (lowest distance, Case A)
    case_a = [e for e in examples if e["rag_case"] == "A"]
    if case_a:
        best_rag = min(case_a, key=lambda x: x["rag_dist"] or 999)
        best_rag["selection_reason"] = "Best RAG retrieval (Case A, lowest distance)"
        selected.append(best_rag)

    # Example 2: Case B or C (where hybrid routing kicks in)
    case_bc = [e for e in examples if e["hybrid_case"] in ("B", "C")]
    if case_bc:
        ex = case_bc[0]
        ex["selection_reason"] = f"Hybrid routing active (Case {ex['hybrid_case']})"
        selected.append(ex)

    # Example 3: Derja question (Category D)
    derja = [e for e in examples if e["category"] == "D"]
    if derja:
        ex = derja[0]
        ex["selection_reason"] = "Derja/mixed-language question (Category D)"
        selected.append(ex)

    # Example 4: Student coaching question (Category C)
    coaching = [e for e in examples if e["category"] == "C"]
    if coaching and len(selected) < 4:
        ex = coaching[0]
        ex["selection_reason"] = "Informal student coaching question (Category C)"
        selected.append(ex)

    # ── Print selected examples ──
    for i, ex in enumerate(selected, 1):
        print(f"\n  {'─' * 65}")
        print(f"  EXAMPLE {i}: {ex['selection_reason']}")
        print(f"  {'─' * 65}")
        print(f"  Question [{ex['qid']}] ({ex['category']}, {ex['mode']}): {ex['chapter']}")
        print(f"  Q: {ex['question'][:150]}{'...' if len(ex['question']) > 150 else ''}")
        print(f"\n  System comparison:")
        print(f"    RAG:        case={ex['rag_case']}, dist={ex['rag_dist']}, "
              f"conf={ex['rag_confidence']}, time={ex['rag_time']}s, "
              f"len={len(ex['rag_answer'])}")
        print(f"    Prompt-Only: conf={ex['po_confidence']}, "
              f"time={ex['po_time']}s, len={len(ex['po_answer'])}")
        print(f"    Hybrid:     case={ex['hybrid_case']}, source={ex['hybrid_source']}, "
              f"conf={ex['hybrid_confidence']}, time={ex['hybrid_time']}s, "
              f"len={len(ex['hybrid_answer'])}")

        if show_full:
            print(f"\n  ── RAG Answer (first 500 chars) ──")
            print(f"  {ex['rag_answer'][:500]}")
            print(f"\n  ── Prompt-Only Answer (first 500 chars) ──")
            print(f"  {ex['po_answer'][:500]}")
            print(f"\n  ── Hybrid Answer (first 500 chars) ──")
            print(f"  {ex['hybrid_answer'][:500]}")

    return selected


# ═════════════════════════════════════════════════════════════════════════════
#  LaTeX OUTPUT
# ═════════════════════════════════════════════════════════════════════════════

def print_latex_per_question(breakdown: list):
    """Print LaTeX per-question breakdown table."""
    print(f"\n\n{'=' * 70}")
    print("  LaTeX: Per-Question Breakdown Table")
    print(f"{'=' * 70}")

    print(r"""
\begin{table}[H]
\centering
\caption{Per-question retrieval metadata for the RAG and Hybrid systems.
Case: A = strong match ($d \leq 1.2$), B = partial ($1.2 < d \leq 1.6$),
C = no useful match ($d > 1.6$). ``Docs'' = number of documents sent to the LLM.}
\label{tab:per-question-retrieval}
\begin{tabular}{llllrrrl}
\toprule
\textbf{ID} & \textbf{Cat.} & \textbf{Chapter} &
\textbf{RAG} & \textbf{RAG} & \textbf{HYB} & \textbf{HYB} & \textbf{HYB} \\
& & & \textbf{Case} & \textbf{Dist.} & \textbf{Case} & \textbf{Dist.} & \textbf{Source} \\
\midrule""")

    for row in breakdown:
        if row["category"] == "E":
            continue
        chapter_short = row["chapter"][:18]
        rag_d = f"{row['rag_best_distance']:.2f}" if row['rag_best_distance'] else "---"
        hyb_d = f"{row['hybrid_best_distance']:.2f}" if row['hybrid_best_distance'] else "---"
        print(f"{row['question_id']} & {row['category']} & {chapter_short} & "
              f"{row['rag_case']} & {rag_d} & {row['hybrid_case']} & {hyb_d} & --- \\\\")

    print(r"""\bottomrule
\end{tabular}
\end{table}""")


def print_latex_case_distribution(case_data: dict, n_queries: int):
    """Print LaTeX case distribution table."""
    print(r"""
\begin{table}[H]
\centering
\caption{Retrieval routing case distribution across """ + str(n_queries) + r""" graded
queries (categories A--D). Cases: A = strong match, B = partial match,
C = no useful match.}
\label{tab:case-distribution}
\begin{tabular}{lrrr}
\toprule
\textbf{Routing Case} & \textbf{RAG} & \textbf{Hybrid} & \textbf{Description} \\
\midrule""")

    descriptions = {
        "A": "Strong retrieval ($d \\leq 1.2$)",
        "B": "Partial match ($1.2 < d \\leq 1.6$)",
        "C": "No useful match ($d > 1.6$)",
    }
    for case in ["A", "B", "C"]:
        rag_n = case_data["rag_cases"].get(case, 0)
        hyb_n = case_data["hybrid_cases"].get(case, 0)
        desc = descriptions.get(case, "")
        print(f"Case~{case} & {rag_n} & {hyb_n} & {desc} \\\\")

    print(r"""\bottomrule
\end{tabular}
\end{table}""")


def print_latex_qualitative(selected: list):
    """Print LaTeX qualitative example template."""
    print(r"""
% ── Qualitative Examples ──
% Copy and adapt the following for each selected example.
% The full answer texts should be trimmed to ~200 words each for the thesis.""")

    for i, ex in enumerate(selected, 1):
        print(f"""
\\subsubsection*{{Example {i}: {ex['selection_reason']}}}

\\textbf{{Question [{ex['qid']}]}} ({ex['category']}, {ex['mode']}):
\\textit{{{ex['question'][:120]}...}}

\\begin{{itemize}}
    \\item \\textbf{{RAG}} (Case~{ex['rag_case']}, $d={ex['rag_dist']}$):
    \\textit{{[Insert trimmed answer excerpt]}}

    \\item \\textbf{{Prompt-Only}}:
    \\textit{{[Insert trimmed answer excerpt]}}

    \\item \\textbf{{Hybrid}} (Case~{ex['hybrid_case']}, source={ex['hybrid_source']}):
    \\textit{{[Insert trimmed answer excerpt]}}
\\end{{itemize}}""")


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Detailed post-evaluation analysis for thesis")
    parser.add_argument("--eval", type=str,
                        default="evaluation/results/eval_results_latest.json",
                        help="Path to evaluation results JSON")
    parser.add_argument("--grades", type=str, default=None,
                        help="Path to filled grading template (optional)")
    parser.add_argument("--key", type=str, default=None,
                        help="Path to answer key (optional)")
    parser.add_argument("--qualitative", action="store_true",
                        help="Print full answer texts for qualitative examples")
    args = parser.parse_args()

    eval_path = Path(args.eval)
    if not eval_path.is_absolute():
        eval_path = PROJECT_ROOT / eval_path

    if not eval_path.exists():
        print(f"Evaluation results not found: {eval_path}")
        print("Run `python evaluation/run_evaluation.py` first.")
        sys.exit(1)

    with open(eval_path, "r", encoding="utf-8") as f:
        eval_data = json.load(f)

    print(f"Loaded {len(eval_data['results'])} question results from {eval_path.name}")

    # Optionally load grades
    grades_data = None
    key_lookup = None
    if args.grades and args.key:
        grades_path = Path(args.grades)
        key_path = Path(args.key)
        if not grades_path.is_absolute():
            grades_path = PROJECT_ROOT / grades_path
        if not key_path.is_absolute():
            key_path = PROJECT_ROOT / key_path

        if grades_path.exists() and key_path.exists():
            with open(grades_path, "r", encoding="utf-8") as f:
                grades_data = json.load(f)
            with open(key_path, "r", encoding="utf-8") as f:
                key_raw = json.load(f)
            key_lookup = {}
            for entry in key_raw:
                qid = entry["question_id"]
                key_lookup[qid] = {
                    "Systeme X": entry.get("Systeme X", entry.get("Système X", "")),
                    "Systeme Y": entry.get("Systeme Y", entry.get("Système Y", "")),
                    "Systeme Z": entry.get("Systeme Z", entry.get("Système Z", "")),
                    "Système X": entry.get("Système X", ""),
                    "Système Y": entry.get("Système Y", ""),
                    "Système Z": entry.get("Système Z", ""),
                }
            print(f"Loaded teacher grades from {grades_path.name}")

    # ── Run all analyses ──
    breakdown = per_question_breakdown(eval_data, grades_data, key_lookup)
    case_data = case_distribution_analysis(eval_data)
    quality_data = retrieval_quality_analysis(eval_data)
    selected = qualitative_examples(eval_data, show_full=args.qualitative)

    # ── Print LaTeX tables ──
    print(f"\n\n{'=' * 70}")
    print("  LaTeX TABLES (copy into experiments.tex)")
    print(f"{'=' * 70}")

    n_graded = len([r for r in eval_data["results"] if r["category"] != "E"])
    print_latex_per_question(breakdown)
    print_latex_case_distribution(case_data, n_graded)
    if selected:
        print_latex_qualitative(selected)

    # ── Save JSON output ──
    results_dir = PROJECT_ROOT / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = results_dir / f"detailed_analysis_{timestamp}.json"

    output = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "eval_source": str(eval_path),
            "n_questions": len(eval_data["results"]),
        },
        "per_question_breakdown": breakdown,
        "case_distribution": case_data,
        "retrieval_quality": {
            "distance_stats": quality_data["rag_distance_stats"],
            "chapter_match_rate": quality_data["chapter_match_rate"],
        },
        "qualitative_examples": [
            {
                "qid": ex["qid"],
                "category": ex["category"],
                "selection_reason": ex["selection_reason"],
                "rag_case": ex["rag_case"],
                "hybrid_case": ex["hybrid_case"],
            }
            for ex in selected
        ],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n\n  Analysis saved to: {output_path}")


if __name__ == "__main__":
    main()
