#!/usr/bin/env python3
"""
Indexes .tex files from GCS into local ChromaDB with BGE-M3 embeddings.
Uses adaptive chunking, rich metadata, and incremental updates via a manifest.

Usage:
  python build_db.py                  # incremental index
  python build_db.py --full_rebuild   # re-index everything
  python build_db.py --stats          # print DB stats
"""

import argparse
import hashlib
import json
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import chromadb
from chromadb import EmbeddingFunction, Documents, Embeddings
from FlagEmbedding import BGEM3FlagModel
from google.cloud import storage

from config import (
    PROJECT_ID, BUCKET_NAME, RAW_PREFIX,
    LOCAL_DB_PATH, COLLECTION_NAME,
    EMBEDDING_MODEL_NAME, EMBEDDING_MAX_LENGTH, EMBEDDING_BATCH_SIZE, USE_FP16,
    CHUNK_CORRECTION, CHUNK_COURS, CHUNK_DEFAULT,
    setup_logging,
)

logger = setup_logging("build_db")

# The manifest tracks what's already indexed — so we can do incremental updates
MANIFEST_PATH = os.path.join(LOCAL_DB_PATH, "index_manifest.json")


# ══════════════════════════════════════════════
# Embedding function (BGE-M3)
# ══════════════════════════════════════════════

# Why BGE-M3: it's multilingual (handles French + Derja + LaTeX mixed text)
# and produces 1024-dim dense vectors. We tested Google text-embedding-005 too
# but BGE-M3 was 4x more consistent on variable name changes (u_n -> v_n).
class BGEM3EmbeddingFunction(EmbeddingFunction):
    """Wraps BAAI/bge-m3 for ChromaDB. Loaded once, reused for all calls."""

    def __init__(self):
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME} (fp16={USE_FP16})")
        t0 = time.monotonic()
        self.model = BGEM3FlagModel(EMBEDDING_MODEL_NAME, use_fp16=USE_FP16)
        logger.info(f"Embedding model loaded in {time.monotonic() - t0:.1f}s")

    def __call__(self, input: Documents) -> Embeddings:
        out = self.model.encode(
            input,
            batch_size=EMBEDDING_BATCH_SIZE,
            max_length=EMBEDDING_MAX_LENGTH,
        )
        return out["dense_vecs"].tolist()


# ══════════════════════════════════════════════
# Manifest (incremental index state)
# ══════════════════════════════════════════════
# The manifest is a JSON file that remembers which files have been indexed
# and what their content hash was. This way, re-running the script only
# processes new or changed files (saves time and embedding API cost).

def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def load_manifest() -> Dict[str, Dict]:
    if not os.path.exists(MANIFEST_PATH):
        return {}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: Dict[str, Dict]):
    _ensure_dir(os.path.dirname(MANIFEST_PATH))
    # Write to .tmp first, then rename — atomic on POSIX, prevents corruption
    # if the script crashes mid-write
    tmp = MANIFEST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MANIFEST_PATH)


# ══════════════════════════════════════════════
# Text processing
# ══════════════════════════════════════════════

def normalize_tex(tex: str) -> str:
    """Clean up whitespace inconsistencies from OCR output."""
    tex = tex.replace("\r\n", "\n").replace("\r", "\n")
    tex = re.sub(r"[ \t]+", " ", tex)       # collapse multiple spaces/tabs
    tex = re.sub(r"\n{3,}", "\n\n", tex)    # max 2 newlines in a row
    return tex.strip()


def sha256_hex(text: str) -> str:
    """Content hash — used to detect if a file changed even if GCS generation changed."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks, trying to break at natural boundaries.
    Why overlap: so that a theorem that starts at the end of chunk N is also
    present at the beginning of chunk N+1 — retrieval can find it either way."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    n = len(text)

    while start < n:
        end = min(n, start + chunk_size)
        segment = text[start:end]

        # Try to break at a natural boundary instead of mid-sentence.
        # Priority: paragraph break > line break > sentence end > any space
        if end < n:
            search_start = max(0, len(segment) - int(chunk_size * 0.4))
            sub = segment[search_start:]
            for pattern in ["\n\n", "\n", ". ", " "]:
                pos = sub.rfind(pattern)
                if pos > 0:
                    end = start + search_start + pos + len(pattern)
                    segment = text[start:end]
                    break

        chunk = segment.strip()
        if chunk:
            chunks.append(chunk)

        new_start = end - overlap
        if new_start <= start:
            new_start = start + max(1, chunk_size // 2)
        start = new_start

    return chunks


def get_chunk_params(doc_type: str) -> Tuple[int, int]:
    """Different chunk sizes per document type.
    Why: corrections need small chunks (1500) to keep one exercise per chunk.
    Course material needs big chunks (3000) to keep a full theorem + proof together.
    If we used the same size for both, either exercises would bleed into each other
    or theorems would get cut in half."""
    if doc_type in ("bac_officiel", "serie", "exercice"):
        return CHUNK_CORRECTION["size"], CHUNK_CORRECTION["overlap"]
    elif doc_type == "cours":
        return CHUNK_COURS["size"], CHUNK_COURS["overlap"]
    return CHUNK_DEFAULT["size"], CHUNK_DEFAULT["overlap"]


# ══════════════════════════════════════════════
# Metadata extraction
# ══════════════════════════════════════════════
# All metadata is extracted from the GCS file path (folder names).
# Why: the folder structure encodes chapter, year, session, doc type.
# This metadata is stored alongside each chunk in ChromaDB so we can
# filter at query time (e.g. "only corrections" or "only chapter 6").

def clean_chapter_name(folder: str) -> str:
    """'10_Nombres_complexes' -> 'Nombres complexes'"""
    folder = folder.replace("-", "_").strip("_")
    folder = re.sub(r"^\d{1,3}_", "", folder)   # strip leading number
    folder = folder.replace("_", " ").strip()
    return (folder[:1].upper() + folder[1:]) if folder else "Inconnu"


def extract_chapter(blob_name: str) -> str:
    """Get chapter from the folder structure: BacMath_Raw_Data/<chapter>/..."""
    parts = blob_name.split("/")
    prefix_base = RAW_PREFIX.strip("/")
    if len(parts) >= 2 and parts[0] == prefix_base:
        return clean_chapter_name(parts[1])
    for p in parts:
        if re.match(r"^\d{1,3}_", p):
            return clean_chapter_name(p)
    return "Inconnu"


def guess_doc_type(blob_name: str) -> str:
    """Classify as bac_officiel, serie, cours, or exercice from the path.
    Order matters: check more specific patterns first."""
    n = blob_name.lower()
    if "bac_avec_corrections" in n or re.search(r"bac\d{4}", n):
        return "bac_officiel"
    if "series_et_corrections" in n or "serie" in n:
        return "serie"
    if "/cours/" in n or n.endswith("/cours"):
        return "cours"
    return "exercice"


def detect_is_solution(blob_name: str) -> bool:
    """Is this file a correction/solution? Checked via filename and path patterns.
    Why this matters: during retrieval, the first pass only searches corrections
    (is_solution=true) to find style exemplars."""
    n = blob_name.lower()
    filename = os.path.basename(n)

    if re.search(r"_sol(?=[\s_.(]|$)", filename):
        return True
    if re.search(r"(?:\b|_)corr(?:ig|ection|\.)", filename):
        return True

    if "_sol/" in n or "/sol/" in n:
        return True
    if "bac_avec_corrections" in n:
        return True

    return False


def extract_exercise_key(blob_name: str) -> str:
    """Extract 'S1_EX1' from series filenames.
    Why: this key links an exercise statement to its correction —
    the companion fetch in rag_engine uses this to pair them."""
    filename = os.path.basename(blob_name)
    m = re.search(r"(S\d+_EX?\d+)", filename, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return ""


def parse_bac_tokens(blob_name: str) -> Dict[str, str]:
    """Extract year, session (princ/controle), exercise number from bac paths.
    Example: 'Bac2023_princ_Ex2' -> year=2023, session=principal, exo_id=2"""
    tokens = {"year": "", "session": "", "exo_id": ""}

    m = re.search(r"bac((?:19|20)\d{2})_?(princ|cont)?_?(?:ex(\d+))?", blob_name, re.IGNORECASE)
    if m:
        tokens["year"] = m.group(1) or ""
        tokens["session"] = (m.group(2) or "").lower()
        tokens["exo_id"] = m.group(3) or ""
        return tokens

    # Fallbacks for non-standard naming
    m = re.search(r"((?:19|20)\d{2})", blob_name)
    if m:
        tokens["year"] = m.group(1)

    m = re.search(r"ex(?:ercice)?[\s_-]*(\d+)", blob_name, re.IGNORECASE)
    if m:
        tokens["exo_id"] = m.group(1)

    lower = blob_name.lower()
    if "cont" in lower and "princ" not in lower:
        tokens["session"] = "controle"
    elif "princ" in lower:
        tokens["session"] = "principal"

    return tokens


def extract_group_id(blob_name: str) -> str:
    """Parent folder name — groups exercise + correction chunks together."""
    parts = [p for p in blob_name.split("/") if p]
    if len(parts) >= 2:
        parent = parts[-2]
        return parent
    return os.path.basename(blob_name)


def extract_metadata(blob_name: str) -> Dict[str, str]:
    """Combine all metadata extractors into one dict per chunk."""
    chapter = extract_chapter(blob_name)
    doc_type = guess_doc_type(blob_name)
    bac = parse_bac_tokens(blob_name)
    group_id = extract_group_id(blob_name)
    is_sol = detect_is_solution(blob_name)
    ex_key = extract_exercise_key(blob_name)

    return {
        "type": doc_type,
        "year": bac.get("year", ""),
        "session": bac.get("session", ""),
        "exo_id": bac.get("exo_id", ""),
        "is_solution": str(is_sol).lower(),   # ChromaDB needs strings, not bools
        "chapter": chapter,
        "group_id": group_id,
        "exercise_key": ex_key,
        "filename": os.path.basename(blob_name),
        "blob_name": blob_name,
        "source": f"gs://{BUCKET_NAME}/{blob_name}",
    }


# ══════════════════════════════════════════════
# GCS helpers
# ══════════════════════════════════════════════
def list_tex_blobs(bucket: storage.Bucket) -> List[storage.Blob]:
    blobs = []
    for blob in bucket.list_blobs(prefix=RAW_PREFIX):
        if blob.name.lower().endswith(".tex"):
            blobs.append(blob)
    return blobs


# ══════════════════════════════════════════════
# Stats
# ══════════════════════════════════════════════
def print_stats(manifest: Dict[str, Dict]):
    """Print what's in the database without modifying anything."""
    if not manifest:
        print("Manifest is empty.")
        return

    type_counts = Counter()
    chapter_counts = Counter()
    total_chunks = 0

    for uri, info in manifest.items():
        t = info.get("type", "unknown")
        c = info.get("chapter", "Inconnu")
        nc = info.get("num_chunks", 0)
        type_counts[t] += 1
        chapter_counts[c] += 1
        total_chunks += nc

    print(f"\n{'='*60}")
    print(f"  INDEX STATISTICS")
    print(f"{'='*60}")
    print(f"  Total files indexed: {len(manifest)}")
    print(f"  Total chunks:        {total_chunks}")
    print(f"\n  By document type:")
    for t, c in type_counts.most_common():
        print(f"    {t:20s} : {c}")
    print(f"\n  By chapter:")
    for ch, c in chapter_counts.most_common():
        print(f"    {ch:30s} : {c}")
    print(f"{'='*60}\n")


# ══════════════════════════════════════════════
# Main indexing loop
# ══════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Index .tex files into ChromaDB")
    parser.add_argument("--max_files", type=int, default=0,
                        help="Index at most N .tex files (0 = all)")
    parser.add_argument("--full_rebuild", action="store_true",
                        help="Clear manifest and re-index everything")
    parser.add_argument("--stats", action="store_true",
                        help="Print stats and exit")
    args = parser.parse_args()

    _ensure_dir(LOCAL_DB_PATH)

    # Load manifest (tracks what's already indexed) or clear it for full rebuild
    if args.full_rebuild:
        logger.info("Full rebuild requested — clearing manifest")
        manifest = {}
    else:
        manifest = load_manifest()

    if args.stats:
        print_stats(manifest)
        return

    # ── Download list of .tex files from GCS ──
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    logger.info("Listing .tex blobs from GCS...")
    t0 = time.monotonic()
    tex_blobs = list_tex_blobs(bucket)
    logger.info(f"Found {len(tex_blobs)} .tex blobs in {time.monotonic() - t0:.1f}s")

    if args.max_files:
        tex_blobs = tex_blobs[:args.max_files]

    # ── Set up ChromaDB ──
    client = chromadb.PersistentClient(path=LOCAL_DB_PATH)
    embedding_fn = BGEM3EmbeddingFunction()
    # For full rebuild: delete the old collection so stale chunks are removed
    if args.full_rebuild:
        try:
            client.delete_collection(name=COLLECTION_NAME)
            logger.info(f"Deleted existing collection '{COLLECTION_NAME}' for full rebuild")
        except ValueError:
            pass  # collection doesn't exist yet
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
    )
    logger.info(f"ChromaDB collection '{COLLECTION_NAME}' has {collection.count()} chunks")

    updated = 0
    skipped = 0
    failed = 0
    total_new_chunks = 0
    type_counter = Counter()
    chapter_counter = Counter()

    total_start = time.monotonic()

    for idx, blob in enumerate(tex_blobs, 1):
        blob_name = blob.name
        source_uri = f"gs://{BUCKET_NAME}/{blob_name}"
        generation = str(getattr(blob, "generation", ""))

        # ── Skip check 1: GCS generation unchanged = file hasn't changed ──
        prev = manifest.get(source_uri)
        if prev and prev.get("generation") == generation and not args.full_rebuild:
            skipped += 1
            continue

        try:
            tex = blob.download_as_text(encoding="utf-8")
            tex = normalize_tex(tex)
            if not tex:
                logger.warning(f"Empty .tex, skipping: {blob_name}")
                continue

            # ── Skip check 2: content hash unchanged = same content, different GCS gen ──
            content_hash = sha256_hex(tex)
            if prev and prev.get("content_hash") == content_hash and not args.full_rebuild:
                manifest[source_uri]["generation"] = generation
                skipped += 1
                continue

            # ── Remove old chunks for this file before re-indexing ──
            if prev and prev.get("chunk_ids"):
                try:
                    collection.delete(ids=prev["chunk_ids"])
                except Exception as e:
                    logger.warning(f"Could not delete old chunks for {blob_name}: {e}")

            # ── Extract metadata from the file path ──
            md = extract_metadata(blob_name)
            doc_type = md["type"]
            chapter = md["chapter"]

            # ── Split into chunks (size depends on doc type) ──
            c_size, c_overlap = get_chunk_params(doc_type)
            chunks = chunk_text(tex, c_size, c_overlap)

            # ── Build batch for ChromaDB upsert ──
            ids, docs, metas = [], [], []
            chunk_ids = []
            now_iso = datetime.now(timezone.utc).isoformat()

            for i, ch in enumerate(chunks):
                # Deterministic ID: same file + same chunk index = same ID
                # This makes upsert safe (overwrites existing instead of duplicating)
                doc_id = f"{source_uri}::chunk_{i}"
                ids.append(doc_id)
                docs.append(ch)
                meta = {
                    **md,
                    "chunk_index": str(i),
                    "total_chunks": str(len(chunks)),
                    "generation": generation,
                    "content_hash": content_hash,
                    "ingested_at": now_iso,
                }
                metas.append(meta)
                chunk_ids.append(doc_id)

            # ── Upsert chunks into ChromaDB (in batches of 200) ──
            BATCH = 200
            for b_start in range(0, len(ids), BATCH):
                b_end = b_start + BATCH
                collection.upsert(
                    ids=ids[b_start:b_end],
                    documents=docs[b_start:b_end],
                    metadatas=metas[b_start:b_end],
                )

            # ── Update manifest with what we just indexed ──
            manifest[source_uri] = {
                "generation": generation,
                "content_hash": content_hash,
                "num_chunks": len(chunks),
                "chunk_ids": chunk_ids,
                "type": doc_type,
                "year": md["year"],
                "session": md["session"],
                "chapter": chapter,
                "group_id": md["group_id"],
                "is_solution": md["is_solution"],
                "indexed_at": now_iso,
            }

            updated += 1
            total_new_chunks += len(chunks)
            type_counter[doc_type] += 1
            chapter_counter[chapter] += 1

            logger.info(
                f"[{idx}/{len(tex_blobs)}] {blob_name} | "
                f"type={doc_type} ch={chapter} yr={md['year']} "
                f"sess={md['session']} ex={md['exo_id']} sol={md['is_solution']} "
                f"chunks={len(chunks)} (size={c_size})"
            )

        except Exception as e:
            failed += 1
            logger.error(f"Failed: {blob_name}: {e}")

    save_manifest(manifest)

    elapsed = time.monotonic() - total_start
    logger.info(
        f"\nDone in {elapsed:.1f}s | "
        f"Updated={updated} Skipped={skipped} Failed={failed} | "
        f"New chunks={total_new_chunks} | "
        f"Total in collection={collection.count()} | "
        f"Manifest entries={len(manifest)}"
    )

    if updated > 0:
        print(f"\nNewly indexed by type:")
        for t, c in type_counter.most_common():
            print(f"  {t:20s} : {c} files")
        print(f"\nNewly indexed by chapter:")
        for ch, c in chapter_counter.most_common():
            print(f"  {ch:30s} : {c} files")


if __name__ == "__main__":
    main()
