# OCR Ground Truth Evaluation

## How to create samples

For each sample, create a subdirectory with two files:

```
evaluation/ocr_ground_truth/
  sample_01_complexes_correction/
    ocr.tex         ← copy the Gemini OCR output here
    reference.tex   ← manually correct it (fix math errors, formatting)
  sample_02_suites_cours/
    ocr.tex
    reference.tex
  ...
```

## Recommended sample selection (5-8 samples)

Pick a diverse mix:
1. A Bac correction with dense math (e.g., nombres complexes)
2. A Bac correction with text-heavy reasoning (e.g., suites/récurrence)
3. A course page with theorem statements
4. An exercise with fractions/integrals (hard for OCR)
5. A clean printed document (easy baseline)
6-8. Optional: handwritten corrections, mixed formatting, etc.

## How to run

```bash
python evaluation/ocr_ground_truth_eval.py
```

This computes CER, WER, and LaTeX math accuracy per sample.
