#!/usr/bin/env python3
"""
Generates printable HTML grading sheets with MathJax rendering for the teacher.
"""

import argparse
import json
import html
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── CSS for print-friendly layout ──────────────────────────────────────────
COMMON_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

  * { box-sizing: border-box; }
  body {
    font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #1a1a1a;
    max-width: 210mm;
    margin: 0 auto;
    padding: 15mm;
    background: white;
  }

  h1 {
    text-align: center;
    font-size: 18pt;
    color: #2c3e50;
    border-bottom: 3px solid #2c3e50;
    padding-bottom: 8px;
    margin-bottom: 5px;
  }

  .subtitle {
    text-align: center;
    color: #666;
    font-size: 10pt;
    margin-bottom: 20px;
  }

  .instructions {
    background: #f0f4f8;
    border-left: 4px solid #3498db;
    padding: 12px 16px;
    margin-bottom: 20px;
    font-size: 10pt;
    color: #2c3e50;
  }

  .rubric-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
    font-size: 9pt;
  }
  .rubric-table th {
    background: #2c3e50;
    color: white;
    padding: 6px 10px;
    text-align: left;
  }
  .rubric-table td {
    padding: 6px 10px;
    border: 1px solid #ddd;
  }
  .rubric-table tr:nth-child(even) { background: #f9f9f9; }

  .question-block {
    border: 2px solid #2c3e50;
    border-radius: 8px;
    margin-bottom: 20px;
    page-break-inside: avoid;
    overflow: hidden;
  }

  .question-header {
    background: #2c3e50;
    color: white;
    padding: 8px 14px;
    font-weight: 700;
    font-size: 11pt;
  }
  .question-header .chapter { font-weight: 400; font-size: 9pt; opacity: 0.85; }

  .question-text {
    background: #eef3f8;
    padding: 10px 14px;
    font-weight: 600;
    border-bottom: 1px solid #ccc;
    font-size: 10.5pt;
  }

  .answer-section {
    padding: 10px 14px;
    border-bottom: 1px solid #e0e0e0;
  }
  .answer-section:last-child { border-bottom: none; }

  .system-label {
    font-weight: 700;
    color: #2c3e50;
    font-size: 11pt;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .system-label .badge {
    display: inline-block;
    background: #3498db;
    color: white;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 9pt;
  }
  .system-label .badge-x { background: #e74c3c; }
  .system-label .badge-y { background: #27ae60; }
  .system-label .badge-z { background: #8e44ad; }

  .answer-text {
    background: #fafafa;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
    padding: 10px 12px;
    margin: 6px 0 10px 0;
    font-size: 10pt;
    white-space: pre-wrap;
    overflow-x: auto;
  }

  /* Grading table per question */
  .grading-table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0;
    font-size: 9.5pt;
  }
  .grading-table th {
    background: #34495e;
    color: white;
    padding: 5px 8px;
    text-align: center;
    font-size: 8.5pt;
  }
  .grading-table td {
    border: 1px solid #bbb;
    padding: 5px 8px;
    text-align: center;
  }
  .grading-table td.label-cell {
    text-align: left;
    font-weight: 600;
    background: #f5f5f5;
    width: 25%;
  }
  .grading-table td.score-cell {
    width: 12%;
    height: 28px;
    background: #fffde7;
  }
  .grading-table td.comment-cell {
    text-align: left;
    height: 32px;
    background: #fffde7;
  }

  /* Guardrail specific */
  .verdict-box {
    display: inline-block;
    border: 2px solid #333;
    width: 80px;
    height: 28px;
    margin: 4px 8px;
    vertical-align: middle;
  }

  .page-break { page-break-before: always; }

  @media print {
    body { padding: 10mm; font-size: 10pt; }
    .question-block { page-break-inside: avoid; }
    .no-print { display: none; }
  }

  /* MathJax overrides */
  .MathJax { font-size: 100% !important; }
</style>
"""

MATHJAX_SCRIPT = """
<script>
  window.MathJax = {
    tex: {
      inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
      displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']],
    },
    options: {
      skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre']
    }
  };
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
"""


def _escape(text: str) -> str:
    """HTML-escape text but preserve LaTeX dollar signs for MathJax."""
    # First HTML-escape
    text = html.escape(text, quote=False)
    return text


def _format_math(text: str) -> str:
    """
    Convert common LaTeX patterns so MathJax can render them.
    Wraps standalone math expressions in $...$ if not already wrapped.
    """
    import re

    # Replace \mathbb{X} patterns — keep as-is for MathJax but ensure $ wrapping
    # Replace \\frac, \\vec etc. — these need to be in math mode

    # If text contains LaTeX commands but no $, wrap key patterns
    if '\\' in text and '$' not in text:
        # Wrap \mathbb, \frac, \vec, \int, etc. in inline math
        latex_cmds = [
            r'\\mathbb\{[A-Z]\}',
            r'\\frac\{[^}]*\}\{[^}]*\}',
            r'\\vec\{[^}]*\}',
            r'\\int',
            r'\\sum',
            r'\\lim',
            r'\\infty',
            r'\\sqrt\{[^}]*\}',
        ]
        for cmd in latex_cmds:
            text = re.sub(f'({cmd})', r'$\1$', text)

    # Clean up double-dollar wrapping from nested replacements
    text = text.replace('$$', '$')

    return text


def _badge_class(label: str) -> str:
    if "X" in label:
        return "badge badge-x"
    elif "Y" in label:
        return "badge badge-y"
    return "badge badge-z"


def generate_grading_html(results_dir: Path) -> Path:
    """Generate the main grading HTML with answers + scoring tables."""

    blind_path = results_dir / "blind_grading_sheet.json"
    template_path = results_dir / "grading_template.json"

    with open(blind_path, "r", encoding="utf-8") as f:
        blind_sheets = json.load(f)
    with open(template_path, "r", encoding="utf-8") as f:
        grading_template = json.load(f)

    rubric = grading_template["rubric"]

    # Category labels
    cat_labels = {
        "A": "Questions directes style Bac",
        "B": "Questions nouvelles par chapitre",
        "C": "Questions informelles d'élèves",
        "D": "Questions en Derja / mixte",
    }

    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Grille d'évaluation — Corrections Bac Math</title>
  {COMMON_CSS}
  {MATHJAX_SCRIPT}
</head>
<body>

<h1>Grille d'évaluation aveugle</h1>
<p class="subtitle">Corrections Bac Mathématiques — 15 questions × 3 systèmes anonymes</p>

<div class="instructions">
  <strong>Instructions :</strong> {_escape(grading_template['instructions'])}
</div>

<h2 style="color: #2c3e50;">Critères de notation (0 à 5)</h2>
<table class="rubric-table">
  <tr><th style="width:30%">Critère</th><th>Description</th><th style="width:8%">Échelle</th></tr>
""")

    criterion_labels = {
        "mathematical_correctness": "Exactitude mathématique",
        "reasoning_clarity": "Clarté du raisonnement",
        "pedagogical_quality": "Qualité pédagogique",
        "bac_style_adherence": "Style Bac tunisien",
    }

    for key, info in rubric.items():
        label = criterion_labels.get(key, key)
        parts.append(f"""  <tr>
    <td><strong>{label}</strong></td>
    <td>{_escape(info['description'])}</td>
    <td style="text-align:center">{info['scale']}</td>
  </tr>""")

    parts.append("</table>\n<hr>\n")

    # ── Questions ──────────────────────────────────────────────────────────
    current_cat = None
    for i, sheet in enumerate(blind_sheets):
        cat = sheet["category"]
        if cat != current_cat:
            current_cat = cat
            cat_title = cat_labels.get(cat, cat)
            parts.append(f'\n<div class="page-break"></div>')
            parts.append(f'<h2 style="color:#2c3e50; margin-top:20px;">Catégorie {cat} — {cat_title}</h2>\n')

        qid = sheet["question_id"]
        chapter = sheet.get("chapter", "")
        mode = sheet.get("mode", "")
        mode_label = "Correction" if mode == "correction" else "Coaching"
        question_text = _format_math(_escape(sheet["question"]))

        parts.append(f"""
<div class="question-block">
  <div class="question-header">
    Question {qid} <span class="chapter">— {_escape(chapter)} ({mode_label})</span>
  </div>
  <div class="question-text">{question_text}</div>
""")

        # Answers from each system
        for label in ["Système X", "Système Y", "Système Z"]:
            answer = sheet["answers"].get(label, "[Pas de réponse]")
            answer_html = _format_math(_escape(answer))
            badge_cls = _badge_class(label)

            parts.append(f"""
  <div class="answer-section">
    <div class="system-label"><span class="{badge_cls}">{label}</span></div>
    <div class="answer-text">{answer_html}</div>
  </div>
""")

        # Grading table
        parts.append("""
  <div style="padding: 10px 14px;">
    <table class="grading-table">
      <tr>
        <th>Critère</th>
        <th>Système X</th>
        <th>Système Y</th>
        <th>Système Z</th>
      </tr>
""")
        for key in rubric:
            label = criterion_labels.get(key, key)
            parts.append(f"""      <tr>
        <td class="label-cell">{label}</td>
        <td class="score-cell">&nbsp;/5</td>
        <td class="score-cell">&nbsp;/5</td>
        <td class="score-cell">&nbsp;/5</td>
      </tr>
""")

        parts.append("""      <tr>
        <td class="label-cell">Commentaires</td>
        <td class="comment-cell"></td>
        <td class="comment-cell"></td>
        <td class="comment-cell"></td>
      </tr>
    </table>
  </div>
</div>
""")

    parts.append("""
<div style="text-align:center; margin-top:30px; color:#999; font-size:9pt;">
  Merci pour votre évaluation !
</div>
</body>
</html>""")

    output_path = results_dir / "teacher_grading_sheet.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    return output_path


def generate_guardrail_html(results_dir: Path) -> Path:
    """Generate the guardrail evaluation HTML."""

    guard_path = results_dir / "guardrail_evaluation.json"
    with open(guard_path, "r", encoding="utf-8") as f:
        guardrail_data = json.load(f)

    instructions = guardrail_data["instructions"]
    evaluations = guardrail_data["evaluations"]

    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Évaluation Guardrail — Questions Hors Programme</title>
  {COMMON_CSS}
  {MATHJAX_SCRIPT}
</head>
<body>

<h1>Évaluation des questions hors programme</h1>
<p class="subtitle">4 questions hors programme × 3 systèmes anonymes — Verdict PASS / FAIL</p>

<div class="instructions">
  <strong>Instructions :</strong> {_escape(instructions)}
</div>

<table class="rubric-table">
  <tr><th>Verdict</th><th>Signification</th></tr>
  <tr>
    <td><strong>PASS</strong></td>
    <td>Le système refuse correctement ou signale explicitement que la méthode est hors programme</td>
  </tr>
  <tr>
    <td><strong>FAIL</strong></td>
    <td>Le système utilise la méthode interdite sans avertir que c'est hors programme</td>
  </tr>
</table>
<hr>
""")

    for entry in evaluations:
        qid = entry["question_id"]
        question_text = _format_math(_escape(entry["question"]))
        notes = _escape(entry.get("notes", ""))

        parts.append(f"""
<div class="question-block">
  <div class="question-header">
    Question {qid} — Hors programme
  </div>
  <div class="question-text">
    {question_text}
    <br><em style="font-size:9pt; color:#666;">Note : {notes}</em>
  </div>
""")

        for label in ["Système X", "Système Y", "Système Z"]:
            ans_data = entry["answers"].get(label, {})
            if isinstance(ans_data, dict):
                answer = ans_data.get("answer", "[Pas de réponse]")
            else:
                answer = str(ans_data)

            answer_html = _format_math(_escape(answer))
            badge_cls = _badge_class(label)

            parts.append(f"""
  <div class="answer-section">
    <div class="system-label">
      <span class="{badge_cls}">{label}</span>
      &nbsp;&nbsp; Verdict : <span class="verdict-box"></span>
      <span style="font-size:9pt; color:#888;">(écrire PASS ou FAIL)</span>
    </div>
    <div class="answer-text">{answer_html}</div>
  </div>
""")

        parts.append("""
  <div style="padding: 10px 14px;">
    <strong>Commentaires :</strong>
    <div style="border: 1px solid #ccc; min-height: 40px; margin-top: 4px; background: #fffde7;"></div>
  </div>
</div>
""")

    parts.append("""
<div style="text-align:center; margin-top:30px; color:#999; font-size:9pt;">
  Merci pour votre évaluation !
</div>
</body>
</html>""")

    output_path = results_dir / "teacher_guardrail_sheet.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate printable HTML grading sheets for teachers"
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default="evaluation/results",
        help="Directory containing the blind JSON files",
    )
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = PROJECT_ROOT / results_dir

    # Check required files exist
    required = ["blind_grading_sheet.json", "grading_template.json", "guardrail_evaluation.json"]
    for fname in required:
        fpath = results_dir / fname
        if not fpath.exists():
            print(f"Missing: {fpath}")
            print("Run first: python evaluation/generate_grading_sheets.py")
            sys.exit(1)

    print("Generating teacher-friendly HTML grading sheets...\n")

    grading_path = generate_grading_html(results_dir)
    print(f"  Grading sheet:   {grading_path}")
    print(f"    (15 questions with answers + scoring tables, LaTeX rendered)")

    guardrail_path = generate_guardrail_html(results_dir)
    print(f"  Guardrail sheet: {guardrail_path}")
    print(f"    (4 out-of-scope questions, PASS/FAIL verdict boxes)")

    print(f"\n  HOW TO USE:")
    print(f"    1. Open the HTML files in your browser (Chrome recommended)")
    print(f"    2. The math formulas will render automatically (needs internet for MathJax)")
    print(f"    3. Print to PDF: Ctrl+P → Save as PDF")
    print(f"    4. Or give the HTML files directly to your teacher")
    print(f"    5. Teacher writes scores in the yellow boxes")


if __name__ == "__main__":
    main()
