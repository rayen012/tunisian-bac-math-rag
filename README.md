# Tunisian Bac Math RAG — AI Tutor

Vertical AI Agent for the Tunisian Baccalaureate (Mathematics, Section Math).
An AI tutor that answers **100% within the Tunisian Bac curriculum** and mimics the
"official Tunisian correction redaction style" in French, with Derja motivational hooks.

## Architecture

The project implements **three engines** for comparative evaluation in the thesis:

1. **RAG Engine** (`rag_engine.py`) — Two-stage retrieval-augmented generation
2. **Prompt-Only Engine** (`prompt_only_engine.py`) — Zero-retrieval baseline using curriculum-encoded prompts
3. **Hybrid Engine** (`hybrid_engine.py`) — Adaptive router that selects RAG, hybrid, or prompt-only based on retrieval quality

```
                         ┌──────────────────────┐
                         │   Student Question    │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │   RAG Engine     │  │  Prompt-Only     │  │  Hybrid Engine   │
   │  (rag_engine.py) │  │  Engine          │  │ (hybrid_engine.py│
   │                  │  │ (prompt_only_    │  │                  │
   │  BGE-M3 embed.   │  │  engine.py)      │  │  Three-case      │
   │  + ChromaDB      │  │                  │  │  router:         │
   │  + 2-stage       │  │  Full curriculum │  │  A: RAG-grounded │
   │    retrieval     │  │  in prompt       │  │  B: RAG+Prompt   │
   │  + Gemini LLM    │  │  + Gemini LLM    │  │  C: Prompt-only  │
   └──────────────────┘  └──────────────────┘  └──────────────────┘
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    ▼
                         ┌──────────────────────┐
                         │   Vertex AI Gemini   │
                         │  (temperature=0.15)  │
                         └──────────────────────┘
```

### Data Pipeline

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  digitize.py │────▶│  GCS Bucket  │────▶│  build_db.py   │
│  (OCR/LaTeX) │     │  (.tex files)│     │  (indexing)    │
└─────────────┘     └──────────────┘     └───────┬────────┘
                                                  │
                                                  ▼
                                          ┌────────────────┐
                                          │   ChromaDB     │
                                          │ (local vectors)│
                                          └────────────────┘
```

**Key design decisions:**
- **Two-stage retrieval** (RAG & Hybrid): corrections/bac exercises first (for redaction style mimicry),
  textbook/cours second (for theorem backing). This directly improves curriculum adherence.
- **Adaptive chunking**: smaller chunks (1500) for corrections to preserve exercise boundaries;
  larger chunks (3000) for textbook to keep theorem context intact.
- **Three-engine comparison**: identical Gemini model, temperature, and output format across all
  engines — the only variable is the knowledge source (retrieved context vs. parametric knowledge).
- **Separated engines**: UI-agnostic, testable, reusable from notebooks and CLI scripts.
- **Incremental indexing**: manifest tracks GCS generation + SHA-256 content hash.
  Re-indexing only processes changed files.
- **Syllabus guard**: the system prompt explicitly forbids out-of-program methods and
  includes anti-injection rules for RAG context.

## How to Run

### Prerequisites

```bash
# 1. Python 3.10+
# 2. GCP credentials configured
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

# 3. Install dependencies
pip install -r requirements.txt
```

### Step 1: Digitize raw documents (PDFs/images -> LaTeX)

```bash
# Dry run — see what needs processing
python digitize.py --dry_run

# Process first 50 files
python digitize.py --max_files 50

# Process all pending files
python digitize.py
```

### Step 2: Build/update the vector database

```bash
# Incremental index (only new/changed .tex files)
python build_db.py

# Full rebuild from scratch
python build_db.py --full_rebuild

# View statistics
python build_db.py --stats
```

### Step 3: Run the Streamlit apps

```bash
# RAG engine (default, port 8501)
streamlit run app.py

# Prompt-Only baseline (port 8502)
streamlit run app_prompt_only.py --server.port 8502

# Hybrid engine (port 8503)
streamlit run app_hybrid.py --server.port 8503
```

### Step 4: Run evaluation experiments

```bash
# Run all three engines on the 20-question evaluation bank
python evaluation/run_evaluation.py

# Generate blind grading sheets for the teacher
python evaluation/generate_grading_sheets.py

# Analyze teacher grades (after grading is complete)
python evaluation/analyze_grades.py

# Compare BGE-M3 vs Google embeddings
python evaluation/embedding_comparison.py

# Variable-name sensitivity probe
python evaluation/variable_sensitivity_probe.py

# OCR quality evaluation
python evaluation/ocr_ground_truth_eval.py
```

### Configuration

All configuration is in `config.py`. Key settings:
- `PROJECT_ID`, `BUCKET_NAME`: your GCP project and bucket
- `CHAT_MODEL_ID`: Gemini model for chat (default: `gemini-2.5-flash`)
- `CHUNK_CORRECTION`, `CHUNK_COURS`: chunking parameters per doc type
- `SIMILARITY_GOOD_THRESHOLD`: L2 distance threshold for "good" retrieval match
- `HYBRID_CASE_B_MAX_CONFIDENCE`: confidence cap for weak-retrieval hybrid routing

## File Structure

| File | Purpose |
|------|---------|
| `config.py` | Shared configuration (GCP, ChromaDB, chunking, retrieval, hybrid params) |
| `digitize.py` | OCR pipeline: GCS images/PDFs -> LaTeX via Vertex AI Gemini |
| `build_db.py` | Indexing pipeline: .tex files -> ChromaDB with rich metadata |
| **Engines** | |
| `rag_engine.py` | RAG engine: 2-stage retrieval + prompt compilation + generation |
| `prompt_only_engine.py` | Prompt-Only engine: curriculum-encoded prompts, zero retrieval |
| `hybrid_engine.py` | Hybrid engine: adaptive router (Case A/B/C) combining RAG + Prompt-Only |
| **Streamlit Apps** | |
| `app.py` | Streamlit UI for the RAG engine |
| `app_prompt_only.py` | Streamlit UI for the Prompt-Only engine |
| `app_hybrid.py` | Streamlit UI for the Hybrid engine |
| **Notebook Chat Helpers** | |
| `chat_rag.py` | Minimal chat interface for RAG engine (use in Jupyter) |
| `chat_prompt_only.py` | Minimal chat interface for Prompt-Only engine (use in Jupyter) |
| `chat_hybrid.py` | Minimal chat interface for Hybrid engine (use in Jupyter) |
| **Evaluation Scripts** | |
| `evaluation/eval_questions.py` | 20-question evaluation bank (5 categories A-E) |
| `evaluation/run_evaluation.py` | Run all three engines on the question bank |
| `evaluation/generate_grading_sheets.py` | Generate blind evaluation sheets for human grading |
| `evaluation/analyze_grades.py` | Parse teacher grades and compute per-system/per-category scores |
| `evaluation/embedding_comparison.py` | Compare BGE-M3 vs Google text-embedding-005 retrieval |
| `evaluation/variable_sensitivity_probe.py` | Test embedding robustness to variable name changes (u_n vs v_n) |
| `evaluation/ocr_ground_truth_eval.py` | Evaluate OCR quality (CER, WER, LaTeX accuracy) |
| **Evaluation Notebooks** | |
| `test_rag.ipynb` | Scientific validation of the RAG pipeline (retrieval, generation, timing) |
| `test_prompt_only.ipynb` | Comparative evaluation: RAG vs Prompt-Only |
| `test_hybrid.ipynb` | Three-way comparative evaluation: RAG vs Prompt-Only vs Hybrid |
| **Other** | |
| `run_streamlit.sh` | Shell script to run Streamlit through Vertex AI Workbench proxy |

## Reproducibility

All three engines use the same Gemini model (`gemini-2.5-flash` by default) with
`temperature=0.15` and `max_output_tokens=4096` to ensure fair comparison.

The evaluation notebooks provide structured, reproducible experiments:

- **`test_rag.ipynb`** — End-to-end validation: environment checks, DB contents,
  two-stage retrieval verification, generation quality, timing benchmarks.
- **`test_prompt_only.ipynb`** — Side-by-side RAG vs Prompt-Only: same questions,
  same model, same temperature, blind-format comparison.
- **`test_hybrid.ipynb`** — Three-way comparison: same question set evaluated across
  all three engines, with routing case distribution analysis.

**Note on determinism:** The LLM temperature is set to 0.15 (near-deterministic) across
all engines. While `temperature=0` would provide fully deterministic outputs, 0.15 was
chosen to allow minor stylistic variation while maintaining high reproducibility.
The digitization pipeline (`digitize.py`) uses `temperature=0.0` for exact LaTeX
transcription. There are no other sources of randomness in the system — embeddings
(BGE-M3) and retrieval (ChromaDB L2 distance) are deterministic.

## Thesis Architecture Explanation

This system implements a **Retrieval-Augmented Generation (RAG)** pipeline specifically
designed for the Tunisian Baccalaureate mathematics curriculum. The architecture addresses
three fundamental challenges in educational AI:

1. **Curriculum fidelity**: A two-stage retrieval mechanism first searches corrected
   exercises (bac officiel, series, devoirs) to find style exemplars, then falls back to
   official textbook content for theorem backing. This ensures the AI never uses methods
   outside the Tunisian program.

2. **Redaction style mimicry**: By prioritizing corrections with `is_solution=true` in the
   first retrieval pass, the system learns the exact phrasing conventions ("On a...", "Or...",
   "Donc...", "D'apres...") expected by Tunisian examiners. The prompt compiler includes a
   mimicry decision tree that instructs the LLM to copy the correction style when a similar
   exercise is found (Case A) or construct from theorems when not (Case B).

3. **Robustness and reproducibility**: Incremental indexing with content hashing enables
   reproducible experiments. The `QueryResult` dataclass captures retrieval scores, selected
   documents, timings, and the retrieval case — providing a complete audit trail suitable
   for thesis evaluation and ablation studies.

The Derja "sandwich" (motivational hook at start and end) adds a culturally relevant
pedagogical dimension that distinguishes this system from generic math tutors.
