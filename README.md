# Tunisian Bac Math RAG

This repository contains the code developed for my Bachelor's thesis at the Technical University of Munich (TUM).

The project implements an AI tutor for the Tunisian Baccalaureate mathematics examination (Section Mathématiques). Its purpose is to answer mathematics questions in a way that remains aligned with the official curriculum and with the style of Tunisian Bac corrections. The generated answers are written mainly in French and may include short motivational phrases in Tunisian Derja.

## Pipeline Overview

### End-to-End Pipeline

```
Scanned Exams (PDF/images)
        |
        v
 +-------------+       +-----------------+
 | digitize.py | ----> | .tex files      |
 | (Gemini OCR)|       | (on GCS bucket) |
 +-------------+       +-----------------+
                                |
                                v
                       +---------------+       +------------------+
                       | build_db.py   | ----> | ChromaDB         |
                       | (chunk+embed) |       | (BGE-M3 vectors  |
                       +---------------+       |  + metadata)     |
                                               +------------------+
                                                       |
                             +-------------------------+
                             |            |            |
                             v            v            v
                       +---------+  +---------+  +---------+
                       |   RAG   |  | Prompt  |  | Hybrid  |
                       | Engine  |  |  Only   |  | Engine  |
                       +---------+  +---------+  +---------+
                             |            |            |
                             v            v            v
                       +--------------------------------------+
                       |         Gemini 2.5 Flash             |
                       |      (answer generation, T=0.15)     |
                       +--------------------------------------+
                                        |
                                        v
                                  Student Answer
                              (French + Derja style)
```

### Hybrid Engine Routing

```
Student Question
       |
       v
  Two-Stage Retrieval (via rag_engine)
       |
       v
  Best L2 Distance?
       |
       +--- distance <= 1.2 ---> Case A: use retrieved context directly
       |
       +--- distance <= 1.6 ---> Case B: retrieved context + curriculum prompt
       |
       +--- distance >  1.6 ---> Case C: prompt-only fallback (no retrieval)
```

### Evaluation Pipeline

```
20 questions (5 categories)
       |
       v
  run_evaluation.py  --->  3 systems x 20 questions = 60 answers
       |
       v
  generate_grading_sheets.py  --->  anonymized (Systeme X/Y/Z)
       |
       v
  generate_teacher_pdf.py  --->  printable grading sheets
       |
       v
  Teacher grades blindly (4 criteria, 0-5 scale)
       |
       v
  analyze_grades.py  --->  unblind + compute averages
       |
       v
  detailed_analysis.py  --->  retrieval quality, routing stats
```

## Project Overview

The repository includes three system variants:

- **RAG**: retrieves relevant correction and course-material chunks from a vector database, then generates an answer grounded in that retrieved context.
- **Prompt-Only**: does not use retrieval. Instead, the curriculum constraints and answer style are encoded directly in the system prompt.
- **Hybrid**: starts with retrieval, then routes between three behaviors depending on retrieval quality:
  - **Case A**: strong retrieval, use retrieved context directly
  - **Case B**: partially useful retrieval, combine retrieved context with broader prompt guidance
  - **Case C**: weak retrieval, fall back to the prompt-only strategy

In the evaluation setup, all three variants use the same Gemini generation model and the same generation temperature (`0.15`). The main experimental difference is therefore how domain knowledge is supplied at inference time.

## Prerequisites

Before running the project, make sure you have the following:

- Python 3.10 or higher
- A Google Cloud project with Vertex AI enabled
- Access to a Google Cloud Storage bucket for the corpus
- Valid Google Cloud credentials

Install the Python dependencies with:

```bash
pip install -r requirements.txt
```

Set the Google Cloud credentials environment variable before running the pipeline:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
```

If `requirements.txt` still needs to be generated from the current environment, you can create it with:

```bash
pip freeze > requirements.txt
```

## Data Availability

The full raw corpus is not included in this repository. It consists of scanned Tunisian Bac materials collected for the thesis and stored in a private Google Cloud Storage bucket.

To make the repository easier to inspect without access to the full corpus, the `samples/` directory contains a few example `.tex` files produced by the digitization pipeline. These illustrate the structure of the OCR output and the type of material indexed by the system.

## Repository Structure

### Core Pipeline

- **`config.py`** : Central configuration file. Contains GCP settings, model IDs, chunk sizes, thresholds, and paths.
- **`digitize.py`** : Digitization pipeline. Sends scanned Bac documents (PDFs or images) to Gemini for OCR-like transcription and stores the resulting `.tex` files in Google Cloud Storage.
- **`build_db.py`** : Indexing pipeline. Downloads `.tex` files from Google Cloud Storage, normalizes them, splits them into chunks, embeds them using BGE-M3, and stores them in a local ChromaDB database together with metadata.

### System Variants

- **`rag_engine.py`** : Retrieval-augmented pipeline with two-stage retrieval and answer generation.
- **`prompt_only_engine.py`** : Prompt-only baseline without retrieval.
- **`hybrid_engine.py`** : Hybrid routing system that switches between retrieval-heavy and prompt-only behavior depending on retrieval quality.

### Evaluation Scripts

- **`evaluation/eval_questions.py`** : Defines the 20 evaluation questions across five categories.
- **`evaluation/run_evaluation.py`** : Runs the three systems on the evaluation question set.
- **`evaluation/generate_grading_sheets.py`** : Creates anonymized grading materials for blind evaluation.
- **`evaluation/generate_teacher_pdf.py`** : Produces printable HTML grading sheets for the teacher.
- **`evaluation/analyze_grades.py`** : Unblinds the evaluation and computes average scores.
- **`evaluation/detailed_analysis.py`** : Performs retrieval analysis, including routing behavior and qualitative case review.
- **`evaluation/embedding_comparison.py`** : Compares BGE-M3 with Google text-embedding-005.
- **`evaluation/variable_sensitivity_probe.py`** : Tests whether notation changes such as `u_n` vs. `v_n` affect retrieval behavior.
- **`evaluation/ocr_ground_truth_eval.py`** : Evaluates OCR quality against manually corrected references using metrics such as CER and WER.

## How the Pipeline Works

### 1. Digitize the Exams

`digitize.py` reads raw PDFs and images of Bac exams from a GCS bucket and sends them to Gemini for OCR-like transcription. The output is saved as LaTeX (`.tex`) files back to Google Cloud Storage.

```bash
python digitize.py --dry_run
python digitize.py --max_files 50
python digitize.py
```

Notes:

- `--dry_run` shows which files would be processed
- `--max_files 50` processes only a subset
- running without arguments processes all remaining files

### 2. Build the Vector Database

`build_db.py` downloads the `.tex` files from GCS, splits them into chunks, embeds them with BGE-M3, and stores them in a local ChromaDB database. It also extracts metadata such as chapter, document type, year, and whether the chunk belongs to a correction, so that retrieval can later use filtering in addition to similarity search.

Corrections use smaller chunks (1500 characters) to preserve local exercise structure. Course material uses larger chunks (3000 characters) to preserve theorem context.

The indexing script also tracks what has already been processed through a manifest file, so re-running it only updates new or modified files.

```bash
python build_db.py
python build_db.py --full_rebuild
python build_db.py --stats
```

Notes:

- default mode performs an incremental update
- `--full_rebuild` rebuilds the database from scratch
- `--stats` prints database statistics

### 3. Query the Engines

Each engine exposes the same interface:

```python
engine.query(question, mode)
```

The `mode` argument can be:

- `"correction"` for a concise Bac-style answer
- `"coaching"` for a more explanatory and pedagogical answer

Example:

```python
from rag_engine import TunisianMathRAG

engine = TunisianMathRAG()
result = engine.query(
    "Calculer l'intégrale I = ∫₀¹ x·eˣ dx",
    mode="correction"
)
print(result.answer)
```

The same pattern applies to `TunisianMathPromptOnly` and `TunisianMathHybrid`.

### 4. Run the Evaluation

To reproduce the main evaluation:

```bash
python evaluation/run_evaluation.py
python evaluation/run_evaluation.py --category A
python evaluation/run_evaluation.py --dry-run
```

Notes:

- default mode runs all 20 questions on all 3 systems
- `--category A` restricts the run to one category
- `--dry-run` previews the run without API calls

After running the evaluation, use the following scripts:

```bash
python evaluation/generate_grading_sheets.py
python evaluation/generate_teacher_pdf.py
python evaluation/analyze_grades.py
python evaluation/detailed_analysis.py
```

Additional experiments:

```bash
python evaluation/embedding_comparison.py
python evaluation/variable_sensitivity_probe.py
python evaluation/ocr_ground_truth_eval.py
```

## Configuration

Most settings are defined in `config.py`. The most important ones are:

- **`PROJECT_ID`**, **`BUCKET_NAME`** : Google Cloud project and storage bucket
- **`CHAT_MODEL_ID`** : Gemini generation model ID
- **`SIMILARITY_GOOD_THRESHOLD`** (1.2) and **`SIMILARITY_FALLBACK_THRESHOLD`** (1.6) : L2 distance thresholds used by the hybrid router
- **`CHUNK_CORRECTION`** and **`CHUNK_COURS`** : Chunk sizes for correction material and course material

## Minimal Path to Reproduce the Workflow

A minimal end-to-end run is:

1. Configure `config.py`
2. Set Google Cloud credentials
3. Run `digitize.py`
4. Run `build_db.py`
5. Instantiate one of the engines and call `query(...)`
6. Run `evaluation/run_evaluation.py`
7. Generate grading sheets and analyze results

## Sample LaTeX Files

The `samples/` directory contains a few example `.tex` files from the digitized corpus. These are included so that the OCR output and corpus structure can be inspected without access to the original scanned exam images.

## Roadmap

The current system was built and evaluated as part of a Bachelor's thesis. Several directions could improve it further:

- **Expand the corpus**: add more chapters, more years of Bac exams, and series exercises to increase retrieval coverage
- **Improve chunking**: experiment with semantic chunking instead of fixed character-based splitting, to better preserve logical exercise boundaries
- **Fine-tune embeddings**: train or fine-tune an embedding model on Tunisian Bac math content specifically, rather than relying on a general multilingual model
- **Structured metadata search**: combine vector similarity with structured filters (chapter, year, exercise type) at query time, to reduce retrieval noise
- **Multilingual prompt tuning**: improve the Derja/French prompt balance based on student feedback
- **Interactive mode**: add a conversational interface where the student can ask follow-up questions on the same exercise
- **Better OCR post-processing**: add a LaTeX validation pass after Gemini OCR to catch and fix common transcription errors before indexing

## Thesis Context

This repository accompanies a Bachelor's thesis comparing three approaches to curriculum-aware mathematical question answering for the Tunisian Baccalaureate:

- retrieval-augmented generation
- prompt-only generation
- hybrid retrieval-aware routing

The repository is intended to make the system structure, execution steps, and evaluation pipeline understandable and reproducible.
