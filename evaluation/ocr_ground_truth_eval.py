#!/usr/bin/env python3
"""
Measures OCR quality (CER, WER, LaTeX accuracy) against manually corrected references.
"""

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── Levenshtein distance (no dependencies needed) ─────────────────────────
def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Insertion, deletion, substitution
            curr_row.append(min(
                prev_row[j + 1] + 1,
                curr_row[j] + 1,
                prev_row[j] + (0 if c1 == c2 else 1),
            ))
        prev_row = curr_row
    return prev_row[-1]


# ── Text normalization ────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    """Normalize whitespace for fair comparison."""
    # Collapse multiple whitespace/newlines into single space
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ── Extract LaTeX math expressions ────────────────────────────────────────
def _extract_math(text: str) -> list:
    """Extract all LaTeX math expressions ($...$, $$...$$, \\(...\\), \\[...\\])."""
    patterns = [
        r'\$\$(.+?)\$\$',       # display math $$...$$
        r'\$(.+?)\$',           # inline math $...$
        r'\\\((.+?)\\\)',       # inline \\(...\\)
        r'\\\[(.+?)\\\]',       # display \\[...\\]
    ]
    expressions = []
    for pat in patterns:
        expressions.extend(re.findall(pat, text, re.DOTALL))
    return [_normalize(e) for e in expressions]


# ── Metrics ───────────────────────────────────────────────────────────────
def compute_cer(ocr: str, ref: str) -> float:
    """Character Error Rate = edit_distance(ocr, ref) / len(ref)."""
    ocr_n = _normalize(ocr)
    ref_n = _normalize(ref)
    if len(ref_n) == 0:
        return 0.0 if len(ocr_n) == 0 else 1.0
    dist = _levenshtein(ocr_n, ref_n)
    return dist / len(ref_n)


def compute_wer(ocr: str, ref: str) -> float:
    """Word Error Rate = word_edit_distance(ocr, ref) / len(ref_words)."""
    ocr_words = _normalize(ocr).split()
    ref_words = _normalize(ref).split()
    if len(ref_words) == 0:
        return 0.0 if len(ocr_words) == 0 else 1.0
    dist = _levenshtein(ocr_words, ref_words)
    return dist / len(ref_words)


def compute_latex_accuracy(ocr: str, ref: str) -> tuple:
    """
    LaTeX math expression accuracy.
    Returns (matched, total_in_ref, accuracy).
    Checks how many math expressions in reference appear exactly in OCR.
    """
    ref_math = _extract_math(ref)
    if not ref_math:
        return (0, 0, 1.0)  # No math to check

    ocr_math = _extract_math(ocr)
    ocr_math_set = set(ocr_math)

    matched = sum(1 for expr in ref_math if expr in ocr_math_set)
    accuracy = matched / len(ref_math)
    return (matched, len(ref_math), accuracy)


# ── Main ──────────────────────────────────────────────────────────────────
def evaluate_samples(samples_dir: Path) -> list:
    """Evaluate all sample pairs in the directory."""
    results = []

    sample_dirs = sorted([
        d for d in samples_dir.iterdir()
        if d.is_dir() and (d / "ocr.tex").exists() and (d / "reference.tex").exists()
    ])

    if not sample_dirs:
        print(f"No valid sample pairs found in {samples_dir}")
        print(f"Expected: <sample_dir>/ocr.tex and <sample_dir>/reference.tex")
        sys.exit(1)

    for sample_dir in sample_dirs:
        ocr_text = (sample_dir / "ocr.tex").read_text(encoding="utf-8")
        ref_text = (sample_dir / "reference.tex").read_text(encoding="utf-8")

        cer = compute_cer(ocr_text, ref_text)
        wer = compute_wer(ocr_text, ref_text)
        matched, total, latex_acc = compute_latex_accuracy(ocr_text, ref_text)

        result = {
            "sample": sample_dir.name,
            "cer": cer,
            "wer": wer,
            "latex_matched": matched,
            "latex_total": total,
            "latex_accuracy": latex_acc,
            "ocr_chars": len(ocr_text),
            "ref_chars": len(ref_text),
        }
        results.append(result)

    return results


def print_results(results: list):
    """Print results and LaTeX table."""
    print("=" * 72)
    print("  OCR GROUND TRUTH EVALUATION — Per-Sample Results")
    print("=" * 72)
    print(f"  {'Sample':<20} {'CER':>8} {'WER':>8} {'LaTeX Acc':>10} {'Math Expr':>10}")
    print("  " + "─" * 60)

    total_cer = 0
    total_wer = 0
    total_latex_matched = 0
    total_latex_total = 0

    for r in results:
        math_str = f"{r['latex_matched']}/{r['latex_total']}" if r['latex_total'] > 0 else "n/a"
        print(f"  {r['sample']:<20} {r['cer']:>7.1%} {r['wer']:>7.1%} "
              f"{r['latex_accuracy']:>9.1%} {math_str:>10}")
        total_cer += r['cer']
        total_wer += r['wer']
        total_latex_matched += r['latex_matched']
        total_latex_total += r['latex_total']

    n = len(results)
    avg_cer = total_cer / n
    avg_wer = total_wer / n
    avg_latex = total_latex_matched / total_latex_total if total_latex_total > 0 else 0

    print("  " + "─" * 60)
    print(f"  {'AVERAGE':<20} {avg_cer:>7.1%} {avg_wer:>7.1%} {avg_latex:>9.1%}")
    print(f"\n  Based on {n} ground truth samples.")

    # LaTeX table
    print("\n" + "=" * 72)
    print("  LaTeX-ready table (copy into thesis)")
    print("=" * 72)
    print(r"""
\begin{table}[H]
\centering
\caption{OCR digitization quality: per-sample Character Error Rate (CER),
Word Error Rate (WER), and \LaTeX{} math expression accuracy, measured
against manually corrected reference texts. Lower is better for CER/WER;
higher is better for \LaTeX{} accuracy.}
\label{tab:ocr-quality}
\begin{tabular}{llrrr}
\toprule
\textbf{Sample} & \textbf{Type} & \textbf{CER (\%)} & \textbf{WER (\%)} & \textbf{\LaTeX{} Acc. (\%)} \\
\midrule""")

    for r in results:
        cer_pct = f"{r['cer']*100:.1f}"
        wer_pct = f"{r['wer']*100:.1f}"
        lat_pct = f"{r['latex_accuracy']*100:.1f}" if r['latex_total'] > 0 else "---"
        print(f"{r['sample']:<20} & TODO & {cer_pct} & {wer_pct} & {lat_pct} \\\\")

    print(r"""\midrule
\textbf{Average} & --- & """ + f"{avg_cer*100:.1f}" + r""" & """ + f"{avg_wer*100:.1f}" + r""" & """ + f"{avg_latex*100:.1f}" + r""" \\
\bottomrule
\end{tabular}
\end{table}""")

    return avg_cer, avg_wer, avg_latex


def main():
    parser = argparse.ArgumentParser(description="OCR ground truth evaluation")
    parser.add_argument(
        "--samples-dir",
        type=str,
        default="evaluation/ocr_ground_truth",
        help="Directory containing sample_XX/ocr.tex + reference.tex pairs",
    )
    args = parser.parse_args()

    samples_dir = Path(args.samples_dir)
    if not samples_dir.is_absolute():
        samples_dir = PROJECT_ROOT / samples_dir

    if not samples_dir.exists():
        print(f"Samples directory not found: {samples_dir}")
        print(f"\nTo set up ground truth evaluation:")
        print(f"  mkdir -p {samples_dir}/sample_01")
        print(f"  # Copy a Gemini OCR output to: {samples_dir}/sample_01/ocr.tex")
        print(f"  # Manually correct it to:      {samples_dir}/sample_01/reference.tex")
        print(f"  # Repeat for 5-8 samples, then re-run this script.")
        sys.exit(1)

    print(f"Evaluating OCR ground truth from: {samples_dir}\n")
    results = evaluate_samples(samples_dir)
    print_results(results)


if __name__ == "__main__":
    main()
