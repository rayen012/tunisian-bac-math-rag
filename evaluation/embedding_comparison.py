#!/usr/bin/env python3
"""
embedding_comparison.py
-----------------------
Compare BGE-M3 (local) vs Google text-embedding (Vertex AI) for retrieval
quality on the Tunisian Bac Math corpus.

Experiment:
  1. Embed the 16 graded evaluation questions (A-D) with both models.
  2. For each query, retrieve top-k from ChromaDB (BGE-M3) and from a
     temporary Google-embedding collection.
  3. Compare: L2 distance distributions, overlap in retrieved docs,
     per-category retrieval quality.

Output:
  evaluation/results/embedding_comparison_YYYYMMDD_HHMMSS.json
  Console tables + LaTeX-ready comparison table.

Usage:
  python evaluation/embedding_comparison.py
  python evaluation/embedding_comparison.py --k 10
  python evaluation/embedding_comparison.py --dry-run
"""

import argparse
import json
import os
import sys
import time
import tempfile
import shutil
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
from evaluation.eval_questions import EVAL_QUESTIONS


# ── Google Vertex AI Embedding ──────────────────────────────────────────────

def get_google_embeddings(texts: list[str], task: str = "RETRIEVAL_QUERY") -> list[list[float]]:
    """Embed texts using Google's text-embedding model via Vertex AI.

    Args:
        texts: List of strings to embed.
        task: One of RETRIEVAL_QUERY, RETRIEVAL_DOCUMENT, SEMANTIC_SIMILARITY, etc.

    Returns:
        List of embedding vectors.
    """
    from vertexai.language_models import TextEmbeddingModel

    model = TextEmbeddingModel.from_pretrained("text-embedding-005")
    # Google API supports batches of up to 250 texts
    all_embeddings = []
    batch_size = 50
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings = model.get_embeddings(batch, output_dimensionality=768)
        all_embeddings.extend([e.values for e in embeddings])
        if i + batch_size < len(texts):
            time.sleep(0.5)  # Rate limit courtesy
    return all_embeddings


def get_bge_m3_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed texts using BGE-M3 (same model as production RAG pipeline)."""
    from FlagEmbedding import BGEM3FlagModel

    model = BGEM3FlagModel(
        config.EMBEDDING_MODEL_NAME,
        use_fp16=config.USE_FP16,
    )
    output = model.encode(
        texts,
        batch_size=config.EMBEDDING_BATCH_SIZE,
        max_length=config.EMBEDDING_MAX_LENGTH,
    )
    # BGE-M3 returns dict with 'dense_vecs' key
    if isinstance(output, dict):
        return output["dense_vecs"].tolist()
    return output.tolist()


# ── ChromaDB Retrieval ──────────────────────────────────────────────────────

def retrieve_with_bge_m3(query: str, k: int = 10):
    """Retrieve from the production ChromaDB collection using BGE-M3.

    Returns list of (distance, metadata) tuples.
    """
    import chromadb
    from rag_engine import BGEM3EmbeddingFunction

    client = chromadb.PersistentClient(path=config.LOCAL_DB_PATH)
    ef = BGEM3EmbeddingFunction()
    collection = client.get_collection(
        name=config.COLLECTION_NAME,
        embedding_function=ef,
    )

    results = collection.query(
        query_texts=[query],
        n_results=k,
        include=["metadatas", "distances", "documents"],
    )

    docs = []
    if results and results["ids"] and results["ids"][0]:
        for i, doc_id in enumerate(results["ids"][0]):
            docs.append({
                "id": doc_id,
                "distance": results["distances"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "text_preview": (results["documents"][0][i][:200]
                                 if results["documents"] and results["documents"][0] else ""),
            })
    return docs


def retrieve_with_google_embedding(query: str, collection_texts: list,
                                    collection_metas: list,
                                    collection_ids: list,
                                    query_emb: list[float],
                                    doc_embs: np.ndarray,
                                    k: int = 10):
    """Retrieve using Google embeddings via brute-force L2 search.

    Since the production ChromaDB uses BGE-M3, we do a manual nearest-neighbor
    search with precomputed Google embeddings for a fair comparison.
    """
    query_vec = np.array(query_emb, dtype=np.float32)
    # L2 distance (squared, same as ChromaDB default)
    distances = np.sum((doc_embs - query_vec) ** 2, axis=1)
    top_k_indices = np.argsort(distances)[:k]

    docs = []
    for idx in top_k_indices:
        docs.append({
            "id": collection_ids[idx],
            "distance": float(distances[idx]),
            "metadata": collection_metas[idx],
            "text_preview": collection_texts[idx][:200],
        })
    return docs


# ── Analysis ────────────────────────────────────────────────────────────────

def compute_overlap(bge_docs: list, google_docs: list, k: int = 5) -> dict:
    """Compute overlap metrics between two retrieval result lists."""
    bge_ids = set(d["id"] for d in bge_docs[:k])
    google_ids = set(d["id"] for d in google_docs[:k])

    overlap = bge_ids & google_ids
    return {
        "overlap_count": len(overlap),
        "overlap_ratio": len(overlap) / k if k > 0 else 0,
        "bge_only": list(bge_ids - google_ids),
        "google_only": list(google_ids - bge_ids),
    }


def categorize_retrieval(best_distance: float) -> str:
    """Map best L2 distance to hybrid routing case."""
    if best_distance <= config.SIMILARITY_GOOD_THRESHOLD:
        return "A"
    elif best_distance <= config.SIMILARITY_FALLBACK_THRESHOLD:
        return "B"
    else:
        return "C"


# ── Main ────────────────────────────────────────────────────────────────────

def run_comparison(k: int = 10, dry_run: bool = False):
    """Run the full embedding comparison experiment."""
    import vertexai
    vertexai.init(project=config.PROJECT_ID, location=config.REGION)

    # Filter to graded questions only (A-D)
    questions = [q for q in EVAL_QUESTIONS if q["category"] in ("A", "B", "C", "D")]

    print(f"\n{'=' * 70}")
    print(f"  EMBEDDING COMPARISON: BGE-M3 vs Google text-embedding-005")
    print(f"  Questions: {len(questions)} (categories A-D)")
    print(f"  Retrieval k: {k}")
    print(f"{'=' * 70}\n")

    if dry_run:
        for q in questions:
            print(f"  [{q['id']}] ({q['category']}) {q['chapter']}")
            print(f"    {q['question'][:80]}...")
        print(f"\n  (dry-run: no API calls made)")
        return

    # ── Step 1: Load all corpus documents from ChromaDB ──
    print("Step 1: Loading corpus documents from ChromaDB...")
    import chromadb
    from rag_engine import BGEM3EmbeddingFunction

    client = chromadb.PersistentClient(path=config.LOCAL_DB_PATH)
    ef = BGEM3EmbeddingFunction()
    collection = client.get_collection(
        name=config.COLLECTION_NAME,
        embedding_function=ef,
    )

    # Get all documents
    all_data = collection.get(include=["documents", "metadatas"])
    corpus_texts = all_data["documents"]
    corpus_metas = all_data["metadatas"]
    corpus_ids = all_data["ids"]
    n_docs = len(corpus_ids)
    print(f"  Loaded {n_docs} corpus chunks.")

    # ── Step 2: Embed corpus with Google embeddings ──
    print(f"\nStep 2: Embedding {n_docs} corpus chunks with Google text-embedding-005...")
    print("  (This may take a few minutes...)")
    t0 = time.monotonic()
    # Use RETRIEVAL_DOCUMENT task type for corpus
    google_corpus_embs = get_google_embeddings(corpus_texts, task="RETRIEVAL_DOCUMENT")
    google_corpus_array = np.array(google_corpus_embs, dtype=np.float32)
    google_embed_time = time.monotonic() - t0
    print(f"  Done in {google_embed_time:.1f}s | Shape: {google_corpus_array.shape}")

    # ── Step 3: Embed queries with both models and retrieve ──
    print(f"\nStep 3: Running retrieval comparison for {len(questions)} queries...")
    query_texts = [q["question"] for q in questions]

    # Embed all queries with Google
    print("  Embedding queries with Google...")
    google_query_embs = get_google_embeddings(query_texts, task="RETRIEVAL_QUERY")

    results = []

    for i, q in enumerate(questions):
        print(f"\n  [{i+1}/{len(questions)}] {q['id']} — {q['chapter']}")

        # BGE-M3 retrieval (via ChromaDB)
        bge_docs = retrieve_with_bge_m3(q["question"], k=k)

        # Google retrieval (brute-force)
        google_docs = retrieve_with_google_embedding(
            q["question"],
            corpus_texts, corpus_metas, corpus_ids,
            google_query_embs[i], google_corpus_array,
            k=k,
        )

        # Compute metrics
        bge_best = bge_docs[0]["distance"] if bge_docs else 999.0
        google_best = google_docs[0]["distance"] if google_docs else 999.0

        bge_case = categorize_retrieval(bge_best)
        google_case = categorize_retrieval(google_best)

        overlap = compute_overlap(bge_docs, google_docs, k=min(k, 5))

        entry = {
            "question_id": q["id"],
            "category": q["category"],
            "chapter": q["chapter"],
            "mode": q["mode"],
            "question": q["question"][:100],
            "bge_m3": {
                "best_distance": round(bge_best, 4),
                "routing_case": bge_case,
                "top_k_distances": [round(d["distance"], 4) for d in bge_docs[:k]],
                "top_k_types": [d["metadata"].get("type", "") for d in bge_docs[:k]],
                "top_k_chapters": [d["metadata"].get("chapter", "") for d in bge_docs[:k]],
                "top_k_is_solution": [d["metadata"].get("is_solution", "") for d in bge_docs[:k]],
            },
            "google": {
                "best_distance": round(google_best, 4),
                "routing_case": google_case,
                "top_k_distances": [round(d["distance"], 4) for d in google_docs[:k]],
                "top_k_types": [d["metadata"].get("type", "") for d in google_docs[:k]],
                "top_k_chapters": [d["metadata"].get("chapter", "") for d in google_docs[:k]],
                "top_k_is_solution": [d["metadata"].get("is_solution", "") for d in google_docs[:k]],
            },
            "overlap": {
                "top5_overlap_count": overlap["overlap_count"],
                "top5_overlap_ratio": round(overlap["overlap_ratio"], 2),
            },
        }
        results.append(entry)

        print(f"    BGE-M3:  best_dist={bge_best:.4f} case={bge_case}")
        print(f"    Google:  best_dist={google_best:.4f} case={google_case}")
        print(f"    Overlap: {overlap['overlap_count']}/5 top-5 docs shared")

    # ── Step 4: Aggregate statistics ──
    print(f"\n\n{'=' * 70}")
    print("  AGGREGATE RESULTS")
    print(f"{'=' * 70}")

    bge_dists = [r["bge_m3"]["best_distance"] for r in results]
    google_dists = [r["google"]["best_distance"] for r in results]
    overlaps = [r["overlap"]["top5_overlap_ratio"] for r in results]

    bge_cases = defaultdict(int)
    google_cases = defaultdict(int)
    for r in results:
        bge_cases[r["bge_m3"]["routing_case"]] += 1
        google_cases[r["google"]["routing_case"]] += 1

    print(f"\n  {'Metric':<35s} {'BGE-M3':>12s} {'Google':>12s}")
    print(f"  {'─' * 59}")
    print(f"  {'Mean best L2 distance':<35s} {np.mean(bge_dists):>12.4f} {np.mean(google_dists):>12.4f}")
    print(f"  {'Median best L2 distance':<35s} {np.median(bge_dists):>12.4f} {np.median(google_dists):>12.4f}")
    print(f"  {'Min best L2 distance':<35s} {np.min(bge_dists):>12.4f} {np.min(google_dists):>12.4f}")
    print(f"  {'Max best L2 distance':<35s} {np.max(bge_dists):>12.4f} {np.max(google_dists):>12.4f}")
    print(f"  {'Std dev best distance':<35s} {np.std(bge_dists):>12.4f} {np.std(google_dists):>12.4f}")

    print(f"\n  Case distribution:")
    for case in ["A", "B", "C"]:
        print(f"    Case {case}: BGE-M3={bge_cases[case]:>2d}/{len(results)}, "
              f"Google={google_cases[case]:>2d}/{len(results)}")

    print(f"\n  Mean top-5 overlap ratio: {np.mean(overlaps):.2f}")

    # Per-category comparison
    print(f"\n  Per-category mean best distance:")
    for cat in "ABCD":
        cat_results = [r for r in results if r["category"] == cat]
        if cat_results:
            bge_avg = np.mean([r["bge_m3"]["best_distance"] for r in cat_results])
            google_avg = np.mean([r["google"]["best_distance"] for r in cat_results])
            print(f"    Cat {cat}: BGE-M3={bge_avg:.4f}, Google={google_avg:.4f}")

    # ── Step 5: Save results ──
    results_dir = PROJECT_ROOT / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = results_dir / f"embedding_comparison_{timestamp}.json"

    output = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bge_model": config.EMBEDDING_MODEL_NAME,
            "google_model": "text-embedding-005",
            "bge_embedding_dim": 1024,
            "google_embedding_dim": 768,
            "retrieval_k": k,
            "n_corpus_chunks": n_docs,
            "n_queries": len(questions),
            "google_embedding_time_s": round(google_embed_time, 1),
            "thresholds": {
                "good": config.SIMILARITY_GOOD_THRESHOLD,
                "fallback": config.SIMILARITY_FALLBACK_THRESHOLD,
            },
        },
        "aggregate": {
            "bge_m3": {
                "mean_best_distance": round(float(np.mean(bge_dists)), 4),
                "median_best_distance": round(float(np.median(bge_dists)), 4),
                "std_best_distance": round(float(np.std(bge_dists)), 4),
                "case_distribution": dict(bge_cases),
            },
            "google": {
                "mean_best_distance": round(float(np.mean(google_dists)), 4),
                "median_best_distance": round(float(np.median(google_dists)), 4),
                "std_best_distance": round(float(np.std(google_dists)), 4),
                "case_distribution": dict(google_cases),
            },
            "mean_top5_overlap": round(float(np.mean(overlaps)), 2),
        },
        "per_query": results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {output_path}")

    # Also save as latest
    latest_path = results_dir / "embedding_comparison_latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  Also saved as: {latest_path}")

    # ── Step 6: Print LaTeX table ──
    print_latex_table(results, bge_cases, google_cases, bge_dists, google_dists, overlaps)

    return output_path


def print_latex_table(results, bge_cases, google_cases, bge_dists, google_dists, overlaps):
    """Print LaTeX-ready comparison tables for the thesis."""
    print(f"\n\n{'=' * 70}")
    print("  LaTeX-ready tables (copy into thesis)")
    print(f"{'=' * 70}")

    # Table 1: Per-query comparison
    print(r"""
% ── Table: Per-query embedding comparison ──
\begin{table}[H]
\centering
\caption{Per-query best L2 distance and routing case for BGE-M3 (production)
vs.\ Google text-embedding-005. Lower distance = better retrieval match.
Cases: A = strong ($\leq 1.2$), B = weak ($\leq 1.6$), C = no match ($> 1.6$).}
\label{tab:embedding-per-query}
\begin{tabular}{llrrlrl}
\toprule
\textbf{ID} & \textbf{Cat.} & \multicolumn{2}{c}{\textbf{BGE-M3}} & & \multicolumn{2}{c}{\textbf{Google}} \\
\cmidrule(lr){3-4} \cmidrule(lr){6-7}
& & \textbf{Best dist.} & \textbf{Case} & & \textbf{Best dist.} & \textbf{Case} \\
\midrule""")

    for r in results:
        qid = r["question_id"]
        cat = r["category"]
        bge_d = r["bge_m3"]["best_distance"]
        bge_c = r["bge_m3"]["routing_case"]
        g_d = r["google"]["best_distance"]
        g_c = r["google"]["routing_case"]
        print(f"{qid} & {cat} & {bge_d:.4f} & {bge_c} & & {g_d:.4f} & {g_c} \\\\")

    print(r"""\midrule
\textbf{Mean} & & \textbf{""" + f"{np.mean(bge_dists):.4f}" + r"""} & & & \textbf{""" +
          f"{np.mean(google_dists):.4f}" + r"""} & \\
\bottomrule
\end{tabular}
\end{table}""")

    # Table 2: Aggregate summary
    print(r"""
% ── Table: Aggregate embedding comparison ──
\begin{table}[H]
\centering
\caption{Aggregate comparison of BGE-M3 vs.\ Google text-embedding-005 for
retrieval on the Tunisian Bac Math corpus (""" + str(len(results)) + r""" queries,
""" + "903" + r""" corpus chunks).}
\label{tab:embedding-aggregate}
\begin{tabular}{lrr}
\toprule
\textbf{Metric} & \textbf{BGE-M3} & \textbf{Google} \\
\midrule
Embedding dimension      & 1024 & 768 \\
Mean best L2 distance    & """ + f"{np.mean(bge_dists):.4f}" + " & " + f"{np.mean(google_dists):.4f}" + r""" \\
Median best L2 distance  & """ + f"{np.median(bge_dists):.4f}" + " & " + f"{np.median(google_dists):.4f}" + r""" \\
Queries in Case~A        & """ + f"{bge_cases['A']}" + " & " + f"{google_cases['A']}" + r""" \\
Queries in Case~B        & """ + f"{bge_cases['B']}" + " & " + f"{google_cases['B']}" + r""" \\
Queries in Case~C        & """ + f"{bge_cases['C']}" + " & " + f"{google_cases['C']}" + r""" \\
Mean top-5 overlap ratio & \multicolumn{2}{c}{""" + f"{np.mean(overlaps):.2f}" + r"""} \\
\bottomrule
\end{tabular}
\end{table}""")


def main():
    parser = argparse.ArgumentParser(
        description="Compare BGE-M3 vs Google text-embedding for Tunisian Bac Math retrieval")
    parser.add_argument("--k", type=int, default=10,
                        help="Number of documents to retrieve per query (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show questions without calling APIs")
    args = parser.parse_args()

    run_comparison(k=args.k, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
