# Tunisian Bac Math RAG — AI Tutor

Vertical AI Agent for the Tunisian Baccalaureate (Mathematics, Section Math).
An AI tutor that answers **100% within the Tunisian Bac curriculum** and mimics the
"official Tunisian correction redaction style" in French, with Derja motivational hooks.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  digitize.py │────▶│  GCS Bucket  │────▶│  build_db.py   │
│  (OCR/LaTeX) │     │  (.tex files)│     │  (indexing)    │
└─────────────┘     └──────────────┘     └───────┬────────┘
                                                  │
                                                  ▼
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│   app.py    │◀───▶│ rag_engine.py│◀───▶│   ChromaDB     │
│ (Streamlit) │     │ (2-stage RAG)│     │ (local vectors)│
└─────────────┘     └──────┬───────┘     └────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Vertex AI   │
                    │  Gemini LLM  │
                    └──────────────┘
```

**Key design decisions:**
- **Two-stage retrieval**: corrections/bac exercises first (for redaction style mimicry),
  textbook/cours second (for theorem backing). This directly improves curriculum adherence.
- **Adaptive chunking**: smaller chunks (1500) for corrections to preserve exercise boundaries;
  larger chunks (3000) for textbook to keep theorem context intact.
- **Separated RAG engine** (`rag_engine.py`): UI-agnostic, testable, reusable from notebooks.
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

### Step 1: Digitize raw documents (PDFs/images → LaTeX)

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

### Step 3: Run the Streamlit app

```bash
streamlit run app.py
```

### Configuration

All configuration is in `config.py`. Key settings:
- `PROJECT_ID`, `BUCKET_NAME`: your GCP project and bucket
- `CHAT_MODEL_ID`: Gemini model for chat (default: `gemini-2.0-flash-exp`)
- `CHUNK_CORRECTION`, `CHUNK_TEXTBOOK`: chunking parameters per doc type
- `SIMILARITY_GOOD_THRESHOLD`: L2 distance threshold for "good" retrieval match

## File Structure

| File | Purpose |
|------|---------|
| `config.py` | Shared configuration (GCP, ChromaDB, chunking, retrieval params) |
| `digitize.py` | OCR pipeline: GCS images/PDFs → LaTeX via Vertex AI Gemini |
| `build_db.py` | Indexing pipeline: .tex files → ChromaDB with rich metadata |
| `rag_engine.py` | Core RAG engine: 2-stage retrieval + prompt compilation + generation |
| `app.py` | Streamlit UI (thin layer over rag_engine) |

## Thesis Architecture Explanation

This system implements a **Retrieval-Augmented Generation (RAG)** pipeline specifically
designed for the Tunisian Baccalaureate mathematics curriculum. The architecture addresses
three fundamental challenges in educational AI:

1. **Curriculum fidelity**: A two-stage retrieval mechanism first searches corrected
   exercises (bac officiel, series, devoirs) to find style exemplars, then falls back to
   official textbook content for theorem backing. This ensures the AI never uses methods
   outside the Tunisian program.

2. **Redaction style mimicry**: By prioritizing corrections with `is_solution=true` in the
   first retrieval pass, the system learns the exact phrasing conventions ("On a…", "Or…",
   "Donc…", "D'après…") expected by Tunisian examiners. The prompt compiler includes a
   mimicry decision tree that instructs the LLM to copy the correction style when a similar
   exercise is found (Case A) or construct from theorems when not (Case B).

3. **Robustness and reproducibility**: Incremental indexing with content hashing enables
   reproducible experiments. The `QueryResult` dataclass captures retrieval scores, selected
   documents, timings, and the retrieval case — providing a complete audit trail suitable
   for thesis evaluation and ablation studies.

The Derja "sandwich" (motivational hook at start and end) adds a culturally relevant
pedagogical dimension that distinguishes this system from generic math tutors.
