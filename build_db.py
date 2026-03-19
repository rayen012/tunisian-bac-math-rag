#!/usr/bin/env python3
"""
build_db.py
-----------
Index .tex files from Google Cloud Storage into local ChromaDB.

Architecture decisions (thesis-grade):
  1. ADAPTIVE CHUNKING: corrections get smaller chunks (1500 chars) to preserve
     exercise boundaries; course material (cours) gets larger chunks (3000) to
     keep theorem context intact.  This directly improves retrieval precision.
  2. RICH METADATA: type / year / chapter / session / exo_id / is_solution /
     group_id / source — enabling filtered retrieval at query time.
  3. INCREMENTAL UPSERT: manifest tracks GCS generation + content SHA-256.
     Only re-embeds files whose content actually changed.  Cuts re-index
     time from hours to seconds for unchanged corpora.
  4. STABLE CHUNK IDs: "{source_uri}::chunk_{i}" — deterministic, so upsert
     replaces the same logical chunk rather than creating duplicates.
  5. CPU-SAFE: auto-detects GPU for fp16; works on laptops.

Usage:
  python build_db.py                  # index all .tex files (incremental)
  python build_db.py --max_files 100  # first 100
  python build_db.py --full_rebuild   # wipe manifest, re-index everything
  python build_db.py --stats          # print DB stats without indexing
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

MANIFEST_PATH = os.path.join(LOCAL_DB_PATH, "index_manifest.json")


# ══════════════════════════════════════════════
# Embedding function (BGE-M3)
# ══════════════════════════════════════════════
class BGEM3EmbeddingFunction(EmbeddingFunction):
    """Wraps BAAI/bge-m3 for ChromaDB.  Instantiated once, reused."""

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
def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def load_manifest() -> Dict[str, Dict]:
    if not os.path.exists(MANIFEST_PATH):
        return {}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest: Dict[str, Dict]):
    _ensure_dir(os.path.dirname(MANIFEST_PATH))
    tmp = MANIFEST_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    os.replace(tmp, MANIFEST_PATH)  # atomic on POSIX


# ══════════════════════════════════════════════
# Text processing
# ══════════════════════════════════════════════
def normalize_tex(tex: str) -> str:
    tex = tex.replace("\r\n", "\n").replace("\r", "\n")
    tex = re.sub(r"[ \t]+", " ", tex)
    tex = re.sub(r"\n{3,}", "\n\n", tex)
    return tex.strip()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks, preferring paragraph/sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    n = len(text)

    while start < n:
        end = min(n, start + chunk_size)
        segment = text[start:end]

        # Try to break at a natural boundary (paragraph > line > sentence)
        if end < n:
            # Search for best boundary in the last 40% of the segment
            search_start = max(0, len(segment) - int(chunk_size * 0.4))
            sub = segment[search_start:]
            # Priority: double newline > single newline > ". " > any space
            for pattern in ["\n\n", "\n", ". ", " "]:
                pos = sub.rfind(pattern)
                if pos > 0:
                    end = start + search_start + pos + len(pattern)
                    segment = text[start:end]
                    break

        chunk = segment.strip()
        if chunk:
            chunks.append(chunk)

        # Advance with overlap
        new_start = end - overlap
        if new_start <= start:
            new_start = start + max(1, chunk_size // 2)
        start = new_start

    return chunks


def get_chunk_params(doc_type: str) -> Tuple[int, int]:
    """Return (chunk_size, overlap) based on document type."""
    if doc_type in ("bac_officiel", "serie", "exercice"):
        return CHUNK_CORRECTION["size"], CHUNK_CORRECTION["overlap"]
    elif doc_type == "cours":
        return CHUNK_COURS["size"], CHUNK_COURS["overlap"]
    return CHUNK_DEFAULT["size"], CHUNK_DEFAULT["overlap"]


# ══════════════════════════════════════════════
# Metadata extraction
# ══════════════════════════════════════════════
def clean_chapter_name(folder: str) -> str:
    """'10_Nombres_complexes' -> 'Nombres complexes'"""
    folder = folder.replace("-", "_").strip("_")
    folder = re.sub(r"^\d{1,3}_", "", folder)
    folder = folder.replace("_", " ").strip()
    return (folder[:1].upper() + folder[1:]) if folder else "Inconnu"


def extract_chapter(blob_name: str) -> str:
    parts = blob_name.split("/")
    prefix_base = RAW_PREFIX.strip("/")
    # Expected: BacMath_Raw_Data/<chapter_folder>/...
    if len(parts) >= 2 and parts[0] == prefix_base:
        return clean_chapter_name(parts[1])
    # Fallback: first folder matching digit prefix
    for p in parts:
        if re.match(r"^\d{1,3}_", p):
            return clean_chapter_name(p)
    return "Inconnu"


def guess_doc_type(blob_name: str) -> str:
    """Classify document type from its GCS path."""
    n = blob_name.lower()
    # Order matters: more specific patterns first
    if "bac_avec_corrections" in n or re.search(r"bac\d{4}", n):
        return "bac_officiel"
    if "serie" in n:
        return "serie"
    if "cours" in n or "tome" in n or "manuel" in n:
        return "cours"
    return "exercice"


def detect_is_solution(blob_name: str) -> bool:
    """Check if the path indicates a solution/correction document."""
    n = blob_name.lower()
    indicators = ["_sol/", "_sol.", "_sol_", "/sol/", "corrig", "correction", "_corr/", "_corr."]
    return any(ind in n for ind in indicators)


def parse_bac_tokens(blob_name: str) -> Dict[str, str]:
    """Extract year, session, exercise number from bac-style folder names.

    Handles patterns like:
      Bac2010_cont_Ex3_Sol/
      Bac2010_princ_Ex1/
      Bac2022_Ex2_Sol/
    """
    tokens = {"year": "", "session": "", "exo_id": ""}

    # Full pattern: BacYYYY_(princ|cont)_ExN
    m = re.search(r"bac((?:19|20)\d{2})_?(princ|cont)?_?(?:ex(\d+))?", blob_name, re.IGNORECASE)
    if m:
        tokens["year"] = m.group(1) or ""
        tokens["session"] = (m.group(2) or "").lower()
        tokens["exo_id"] = m.group(3) or ""
        return tokens

    # Fallback: any 4-digit year
    m = re.search(r"((?:19|20)\d{2})", blob_name)
    if m:
        tokens["year"] = m.group(1)

    # Fallback: exercise number anywhere
    m = re.search(r"ex(?:ercice)?[\s_-]*(\d+)", blob_name, re.IGNORECASE)
    if m:
        tokens["exo_id"] = m.group(1)

    # Fallback: session from path
    lower = blob_name.lower()
    if "cont" in lower and "princ" not in lower:
        tokens["session"] = "controle"
    elif "princ" in lower:
        tokens["session"] = "principal"

    return tokens


def extract_group_id(blob_name: str) -> str:
    """Group ID = nearest parent folder containing BacYYYY or a meaningful name.

    Used to link exercise + solution chunks from the same parent folder.
    """
    parts = [p for p in blob_name.split("/") if p]
    if len(parts) >= 2:
        parent = parts[-2]
        return parent
    return os.path.basename(blob_name)


def extract_metadata(blob_name: str) -> Dict[str, str]:
    """Build full metadata dict for a .tex blob."""
    chapter = extract_chapter(blob_name)
    doc_type = guess_doc_type(blob_name)
    bac = parse_bac_tokens(blob_name)
    group_id = extract_group_id(blob_name)
    is_sol = detect_is_solution(blob_name)

    return {
        "type": doc_type,
        "year": bac.get("year", ""),
        "session": bac.get("session", ""),
        "exo_id": bac.get("exo_id", ""),
        "is_solution": str(is_sol).lower(),   # "true"/"false" as string for Chroma
        "chapter": chapter,
        "group_id": group_id,
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
    """Print summary statistics from the manifest."""
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

    # Load or clear manifest
    if args.full_rebuild:
        logger.info("Full rebuild requested — clearing manifest")
        manifest = {}
    else:
        manifest = load_manifest()

    if args.stats:
        print_stats(manifest)
        return

    # ── GCS ──
    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(BUCKET_NAME)
    logger.info("Listing .tex blobs from GCS...")
    t0 = time.monotonic()
    tex_blobs = list_tex_blobs(bucket)
    logger.info(f"Found {len(tex_blobs)} .tex blobs in {time.monotonic() - t0:.1f}s")

    if args.max_files:
        tex_blobs = tex_blobs[:args.max_files]

    # ── ChromaDB ──
    client = chromadb.PersistentClient(path=LOCAL_DB_PATH)
    embedding_fn = BGEM3EmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
    )
    logger.info(f"ChromaDB collection '{COLLECTION_NAME}' has {collection.count()} chunks")

    # ── Counters ──
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

        # ── Check manifest: skip if generation unchanged ──
        prev = manifest.get(source_uri)
        if prev and prev.get("generation") == generation and not args.full_rebuild:
            skipped += 1
            continue

        try:
            # Download and normalize
            tex = blob.download_as_text(encoding="utf-8")
            tex = normalize_tex(tex)
            if not tex:
                logger.warning(f"Empty .tex, skipping: {blob_name}")
                continue

            # Content hash for extra safety
            content_hash = sha256_hex(tex)
            if prev and prev.get("content_hash") == content_hash and not args.full_rebuild:
                # Generation changed but content identical — update generation in manifest, skip embedding
                manifest[source_uri]["generation"] = generation
                skipped += 1
                continue

            # ── Delete old chunks for this file ──
            if prev and prev.get("chunk_ids"):
                try:
                    collection.delete(ids=prev["chunk_ids"])
                except Exception as e:
                    logger.warning(f"Could not delete old chunks for {blob_name}: {e}")

            # ── Metadata ──
            md = extract_metadata(blob_name)
            doc_type = md["type"]
            chapter = md["chapter"]

            # ── Adaptive chunking ──
            c_size, c_overlap = get_chunk_params(doc_type)
            chunks = chunk_text(tex, c_size, c_overlap)

            # ── Build batch ──
            ids, docs, metas = [], [], []
            chunk_ids = []
            now_iso = datetime.now(timezone.utc).isoformat()

            for i, ch in enumerate(chunks):
                # Stable ID: deterministic per file + chunk index
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

            # ── Upsert in batches (Chroma can handle large batches but let's be safe) ──
            BATCH = 200
            for b_start in range(0, len(ids), BATCH):
                b_end = b_start + BATCH
                collection.upsert(
                    ids=ids[b_start:b_end],
                    documents=docs[b_start:b_end],
                    metadatas=metas[b_start:b_end],
                )

            # ── Update manifest ──
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

    # ── Save manifest ──
    save_manifest(manifest)

    elapsed = time.monotonic() - total_start
    logger.info(
        f"\nDone in {elapsed:.1f}s | "
        f"Updated={updated} Skipped={skipped} Failed={failed} | "
        f"New chunks={total_new_chunks} | "
        f"Total in collection={collection.count()} | "
        f"Manifest entries={len(manifest)}"
    )

    # Print summary
    if updated > 0:
        print(f"\nNewly indexed by type:")
        for t, c in type_counter.most_common():
            print(f"  {t:20s} : {c} files")
        print(f"\nNewly indexed by chapter:")
        for ch, c in chapter_counter.most_common():
            print(f"  {ch:30s} : {c} files")


if __name__ == "__main__":
    main()
