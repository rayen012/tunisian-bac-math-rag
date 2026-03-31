"""
Shared configuration for the whole project.
"""

import os
import logging
import torch

# ──────────────────────────────────────────────
# Google Cloud
# ──────────────────────────────────────────────
PROJECT_ID = os.getenv("GCP_PROJECT_ID", "project-e9871d91-8923-44ed-887")
REGION = os.getenv("GCP_REGION", "us-central1")
BUCKET_NAME = os.getenv("GCS_BUCKET", "bucket_1234587")
RAW_PREFIX = "BacMath_Raw_Data/"

# ──────────────────────────────────────────────
# ChromaDB
# ──────────────────────────────────────────────
LOCAL_DB_PATH = os.getenv("CHROMA_DB_PATH", "./tunisian_math_db")
COLLECTION_NAME = "bac_math_exercises"

# ──────────────────────────────────────────────
# Embedding (BGE-M3)
# ──────────────────────────────────────────────
EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_MAX_LENGTH = 8192
EMBEDDING_BATCH_SIZE = 12
# Auto-detect GPU; use fp16 only when CUDA is available
USE_FP16 = torch.cuda.is_available()

# ──────────────────────────────────────────────
# Vertex AI LLM models
# ──────────────────────────────────────────────
CHAT_MODEL_ID = os.getenv("CHAT_MODEL_ID", "gemini-2.5-flash")

# Models for OCR/digitization (in order of preference)
TRANSCRIBE_MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]

# ──────────────────────────────────────────────
# Chunking (different sizes per document type)
# ──────────────────────────────────────────────
CHUNK_CORRECTION = {"size": 1500, "overlap": 200}  # corrections/exercises
CHUNK_COURS = {"size": 3000, "overlap": 250}        # course material
CHUNK_DEFAULT = {"size": 1800, "overlap": 200}

# ──────────────────────────────────────────────
# Retrieval parameters
# ──────────────────────────────────────────────
RETRIEVE_K_FIRST_PASS = 10
RETRIEVE_K_SECOND_PASS = 8
USE_TOP_N = 6
MAX_CHARS_PER_DOC = 2000
MAX_TOTAL_CONTEXT_CHARS = 14000
SIMILARITY_GOOD_THRESHOLD = 1.2   # L2 distance: "good match"
SIMILARITY_FALLBACK_THRESHOLD = 1.6
RETRIEVE_K_COMPANIONS = 3

# ──────────────────────────────────────────────
# Hybrid engine
# ──────────────────────────────────────────────
HYBRID_CASE_B_MAX_CONFIDENCE = "moyen"

# ──────────────────────────────────────────────
# Supported file types for digitization
# ──────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}

# ──────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging(name: str = "bac_math") -> logging.Logger:
    """Configure and return a logger with consistent formatting."""
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format=LOG_FORMAT)
    return logging.getLogger(name)