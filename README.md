# Tunisian Bac Math RAG

This is the code for my Bachelor thesis at TUM. It's an AI math tutor for the Tunisian Baccalaureate (Section Maths) that answers questions using the official curriculum, in French with Tunisian Derja motivational phrases.

The project compares three different approaches to answering math questions:

- **RAG** — retrieves relevant corrections and course material from a vector database, then generates an answer grounded in that context
- **Prompt-Only** — no retrieval at all, just a carefully crafted prompt with the full curriculum encoded directly
- **Hybrid** — tries retrieval first, then decides whether the results are good enough to use (Case A), partially useful (Case B), or useless (Case C, falls back to prompt-only)

All three use the same Gemini model with the same temperature (0.15) so the only variable is where the knowledge comes from.

## Prerequisites

- Python 3.10+
- A GCP project with Vertex AI enabled
- GCP credentials set up (`export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"`)

```bash
pip install -r requirements.txt
```

## How it works (step by step)

### 1. Digitize the exams

`digitize.py` takes raw PDFs and images of Bac exams from a GCS bucket and sends them to Gemini for OCR. The output is clean LaTeX (.tex files) saved back to GCS.

```bash
python digitize.py --dry_run     # see what needs processing
python digitize.py --max_files 50  # process 50 files
python digitize.py                 # process everything
```

### 2. Build the vector database

`build_db.py` downloads the .tex files from GCS, splits them into chunks, embeds them with BGE-M3, and stores everything in a local ChromaDB database. It also extracts metadata (chapter, document type, year, whether it's a correction, etc.) so we can filter at query time.

Corrections get smaller chunks (1500 chars) to keep exercise boundaries clean. Course material gets bigger chunks (3000 chars) to keep theorems intact.

The script tracks what's already been indexed (via a manifest file) so re-running it only processes new or changed files.

```bash
python build_db.py                # incremental update
python build_db.py --full_rebuild # start fresh
python build_db.py --stats        # see what's in the DB
```

### 3. Query the engines

Each engine has the same interface — `engine.query(question, mode)` where mode is either `"correction"` (dry Bac-style answer) or `"coaching"` (more pedagogical).

```python
from rag_engine import TunisianMathRAG
engine = TunisianMathRAG()
result = engine.query("Calculer l'intégrale I = ∫₀¹ x·eˣ dx", mode="correction")
print(result.answer)
```

Same thing works with `TunisianMathPromptOnly` and `TunisianMathHybrid`.

### 4. Run the evaluation

```bash
python evaluation/run_evaluation.py                 # all 20 questions x 3 systems
python evaluation/run_evaluation.py --category A    # just category A
python evaluation/run_evaluation.py --dry-run       # preview without API calls
```

After running the evaluation:

```bash
python evaluation/generate_grading_sheets.py   # create blind grading materials
python evaluation/generate_teacher_pdf.py      # HTML sheets for the teacher
python evaluation/analyze_grades.py            # unblind and compute scores
python evaluation/detailed_analysis.py         # deep dive into retrieval quality
```

Other experiments:

```bash
python evaluation/embedding_comparison.py       # BGE-M3 vs Google embeddings
python evaluation/variable_sensitivity_probe.py # u_n vs v_n sensitivity test
python evaluation/ocr_ground_truth_eval.py      # OCR quality (CER, WER)
```

## File overview

### Core pipeline

| File | What it does |
|------|-------------|
| `config.py` | All settings in one place (GCP config, model IDs, chunking sizes, thresholds) |
| `digitize.py` | OCR pipeline: scanned exams → LaTeX via Gemini |
| `build_db.py` | Indexing pipeline: .tex files → ChromaDB with BGE-M3 embeddings |

### The three engines

| File | What it does |
|------|-------------|
| `rag_engine.py` | Two-stage retrieval (corrections first, then course material) + Gemini generation |
| `prompt_only_engine.py` | Zero retrieval — full Bac curriculum encoded in the prompt |
| `hybrid_engine.py` | Routes to RAG, mixed, or prompt-only based on retrieval quality |

### Evaluation

| File | What it does |
|------|-------------|
| `evaluation/eval_questions.py` | 20 test questions in 5 categories (A: Bac-style, B: novel, C: informal, D: Derja, E: out-of-scope) |
| `evaluation/run_evaluation.py` | Runs all questions through all 3 engines |
| `evaluation/generate_grading_sheets.py` | Creates blind grading materials (Systeme X/Y/Z) |
| `evaluation/generate_teacher_pdf.py` | Printable HTML with MathJax for the teacher |
| `evaluation/analyze_grades.py` | Unblinds scores and computes averages |
| `evaluation/detailed_analysis.py` | Retrieval quality analysis, case distribution, qualitative examples |
| `evaluation/embedding_comparison.py` | BGE-M3 vs Google text-embedding-005 comparison |
| `evaluation/variable_sensitivity_probe.py` | Tests if changing u_n to v_n changes retrieval results |
| `evaluation/ocr_ground_truth_eval.py` | Measures OCR accuracy against manually corrected references |

## Configuration

Everything is in `config.py`. The main things you might want to change:

- `PROJECT_ID`, `BUCKET_NAME` — your GCP project and storage bucket
- `CHAT_MODEL_ID` — which Gemini model to use (default: `gemini-2.5-flash`)
- `SIMILARITY_GOOD_THRESHOLD` (1.2) and `SIMILARITY_FALLBACK_THRESHOLD` (1.6) — L2 distance thresholds for the hybrid router
- `CHUNK_CORRECTION` and `CHUNK_COURS` — chunk sizes per document type

## Sample LaTeX files

The `samples/` directory contains a few example .tex files from the digitized corpus, so you can see what the OCR output looks like without needing access to the full GCS bucket.
