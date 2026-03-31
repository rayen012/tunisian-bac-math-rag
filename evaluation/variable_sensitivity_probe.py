#!/usr/bin/env python3
"""
Tests if swapping variable names (u_n -> v_n) changes retrieval results.
Compares BGE-M3 vs Google embeddings on 6 query pairs.
"""

import argparse
import json
import sys
import time
import numpy as np
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config

# ── Query pairs ─────────────────────────────────────────────────────────────
# Each pair: (original, swapped).  Only the variable letter changes.

QUERY_PAIRS = [
    {
        "id": "P1",
        "topic": "Suite géométrique",
        "original":  "Montrer que la suite $(u_n)$ est une suite géométrique.",
        "swapped":   "Montrer que la suite $(v_n)$ est une suite géométrique.",
        "swap_desc": "u_n → v_n",
    },
    {
        "id": "P2",
        "topic": "Calcul de termes",
        "original":  "Calculer $u_0$, $u_1$ et $u_2$.",
        "swapped":   "Calculer $v_0$, $v_1$ et $v_2$.",
        "swap_desc": "u_n → v_n",
    },
    {
        "id": "P3",
        "topic": "Monotonie",
        "original":  "Étudier la monotonie de la suite $(u_n)$.",
        "swapped":   "Étudier la monotonie de la suite $(w_n)$.",
        "swap_desc": "u_n → w_n",
    },
    {
        "id": "P4",
        "topic": "Forme explicite",
        "original":  "Montrer que pour tout $n \\in \\mathbb{N}$, $u_n = 2^n + 3$.",
        "swapped":   "Montrer que pour tout $n \\in \\mathbb{N}$, $v_n = 2^n + 3$.",
        "swap_desc": "u_n → v_n",
    },
    {
        "id": "P5",
        "topic": "Limite",
        "original":  "Calculer la limite de la suite $(u_n)$.",
        "swapped":   "Calculer la limite de la suite $(v_n)$.",
        "swap_desc": "u_n → v_n",
    },
    {
        "id": "P6",
        "topic": "Suite arithmétique",
        "original":  "Montrer que la suite $(u_n)$ est arithmétique et déterminer sa raison $r$.",
        "swapped":   "Montrer que la suite $(v_n)$ est arithmétique et déterminer sa raison $r$.",
        "swap_desc": "u_n → v_n",
    },
]


# ── Retrieval helpers ───────────────────────────────────────────────────────

def retrieve_bge(query: str, collection, k: int = 3):
    """Retrieve top-k from ChromaDB using BGE-M3 (production embeddings)."""
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
                "chapter": results["metadatas"][0][i].get("chapter", ""),
                "type": results["metadatas"][0][i].get("type", ""),
                "preview": (results["documents"][0][i] or "")[:120],
            })
    return docs


def retrieve_google(query_emb, corpus_embs, corpus_ids, corpus_metas,
                    corpus_texts, k: int = 3):
    """Brute-force top-k retrieval using Google embeddings (L2 squared)."""
    query_vec = np.array(query_emb, dtype=np.float32)
    distances = np.sum((corpus_embs - query_vec) ** 2, axis=1)
    top_k = np.argsort(distances)[:k]
    docs = []
    for idx in top_k:
        docs.append({
            "id": corpus_ids[idx],
            "distance": float(distances[idx]),
            "chapter": corpus_metas[idx].get("chapter", ""),
            "type": corpus_metas[idx].get("type", ""),
            "preview": (corpus_texts[idx] or "")[:120],
        })
    return docs


def top_k_overlap(docs_a, docs_b, k: int = 3):
    """Fraction of shared document IDs in two top-k lists."""
    ids_a = set(d["id"] for d in docs_a[:k])
    ids_b = set(d["id"] for d in docs_b[:k])
    return len(ids_a & ids_b) / k if k > 0 else 0.0


# ── Main experiment ─────────────────────────────────────────────────────────

def run_probe(k: int = 3, dry_run: bool = False):
    print(f"\n{'=' * 65}")
    print("  VARIABLE-SENSITIVITY PROBE")
    print(f"  {len(QUERY_PAIRS)} query pairs, top-{k} retrieval")
    print(f"  BGE-M3 vs Google text-embedding-005")
    print(f"{'=' * 65}\n")

    if dry_run:
        for p in QUERY_PAIRS:
            print(f"  [{p['id']}] {p['topic']}  ({p['swap_desc']})")
            print(f"    A: {p['original'][:70]}...")
            print(f"    B: {p['swapped'][:70]}...")
        print("\n  (dry-run — no API calls)")
        return

    # ── Load corpus from ChromaDB ──
    print("Loading corpus from ChromaDB...")
    import chromadb
    from rag_engine import BGEM3EmbeddingFunction

    client = chromadb.PersistentClient(path=config.LOCAL_DB_PATH)
    ef = BGEM3EmbeddingFunction()
    collection = client.get_collection(
        name=config.COLLECTION_NAME,
        embedding_function=ef,
    )
    all_data = collection.get(include=["documents", "metadatas"])
    corpus_texts = all_data["documents"]
    corpus_metas = all_data["metadatas"]
    corpus_ids = all_data["ids"]
    print(f"  {len(corpus_ids)} chunks loaded.\n")

    # ── Embed corpus with Google ──
    print("Embedding corpus with Google text-embedding-005...")
    import vertexai
    from evaluation.embedding_comparison import get_google_embeddings
    vertexai.init(project=config.PROJECT_ID, location=config.REGION)

    t0 = time.monotonic()
    google_corpus_embs = get_google_embeddings(corpus_texts, task="RETRIEVAL_DOCUMENT")
    google_corpus_array = np.array(google_corpus_embs, dtype=np.float32)
    print(f"  Done in {time.monotonic() - t0:.1f}s\n")

    # ── Embed all probe queries with Google ──
    all_queries = []
    for p in QUERY_PAIRS:
        all_queries.append(p["original"])
        all_queries.append(p["swapped"])
    google_query_embs = get_google_embeddings(all_queries, task="RETRIEVAL_QUERY")

    # ── Run retrieval for each pair ──
    results = []
    for i, pair in enumerate(QUERY_PAIRS):
        print(f"[{pair['id']}] {pair['topic']}  ({pair['swap_desc']})")

        # BGE-M3
        bge_orig = retrieve_bge(pair["original"], collection, k=k)
        bge_swap = retrieve_bge(pair["swapped"], collection, k=k)

        # Google
        g_orig = retrieve_google(
            google_query_embs[2 * i], google_corpus_array,
            corpus_ids, corpus_metas, corpus_texts, k=k)
        g_swap = retrieve_google(
            google_query_embs[2 * i + 1], google_corpus_array,
            corpus_ids, corpus_metas, corpus_texts, k=k)

        # Distance delta (top-1)
        bge_delta = abs(bge_orig[0]["distance"] - bge_swap[0]["distance"]) if bge_orig and bge_swap else None
        g_delta = abs(g_orig[0]["distance"] - g_swap[0]["distance"]) if g_orig and g_swap else None

        # Top-k overlap between original and swapped
        bge_overlap = top_k_overlap(bge_orig, bge_swap, k=k)
        g_overlap = top_k_overlap(g_orig, g_swap, k=k)

        entry = {
            "pair_id": pair["id"],
            "topic": pair["topic"],
            "swap": pair["swap_desc"],
            "bge_m3": {
                "orig_top1_dist": round(bge_orig[0]["distance"], 4) if bge_orig else None,
                "swap_top1_dist": round(bge_swap[0]["distance"], 4) if bge_swap else None,
                "delta": round(bge_delta, 4) if bge_delta is not None else None,
                "top_k_overlap": round(bge_overlap, 2),
                "orig_top1_id": bge_orig[0]["id"] if bge_orig else None,
                "swap_top1_id": bge_swap[0]["id"] if bge_swap else None,
                "same_top1": (bge_orig[0]["id"] == bge_swap[0]["id"]) if bge_orig and bge_swap else None,
            },
            "google": {
                "orig_top1_dist": round(g_orig[0]["distance"], 4) if g_orig else None,
                "swap_top1_dist": round(g_swap[0]["distance"], 4) if g_swap else None,
                "delta": round(g_delta, 4) if g_delta is not None else None,
                "top_k_overlap": round(g_overlap, 2),
                "orig_top1_id": g_orig[0]["id"] if g_orig else None,
                "swap_top1_id": g_swap[0]["id"] if g_swap else None,
                "same_top1": (g_orig[0]["id"] == g_swap[0]["id"]) if g_orig and g_swap else None,
            },
        }
        results.append(entry)

        print(f"  BGE-M3:  Δdist={bge_delta:.4f}  overlap={bge_overlap:.0%}  same_top1={entry['bge_m3']['same_top1']}")
        print(f"  Google:  Δdist={g_delta:.4f}  overlap={g_overlap:.0%}  same_top1={entry['google']['same_top1']}")
        print()

    # ── Aggregate ──
    bge_deltas = [r["bge_m3"]["delta"] for r in results if r["bge_m3"]["delta"] is not None]
    g_deltas = [r["google"]["delta"] for r in results if r["google"]["delta"] is not None]
    bge_overlaps = [r["bge_m3"]["top_k_overlap"] for r in results]
    g_overlaps = [r["google"]["top_k_overlap"] for r in results]
    bge_same = sum(1 for r in results if r["bge_m3"]["same_top1"])
    g_same = sum(1 for r in results if r["google"]["same_top1"])

    print(f"{'=' * 65}")
    print("  SUMMARY")
    print(f"{'=' * 65}")
    print(f"  {'Metric':<30s} {'BGE-M3':>10s} {'Google':>10s}")
    print(f"  {'─' * 50}")
    print(f"  {'Mean |Δ distance|':<30s} {np.mean(bge_deltas):>10.4f} {np.mean(g_deltas):>10.4f}")
    print(f"  {'Max |Δ distance|':<30s} {np.max(bge_deltas):>10.4f} {np.max(g_deltas):>10.4f}")
    print(f"  {'Mean top-{} overlap'.format(k):<30s} {np.mean(bge_overlaps):>10.0%} {np.mean(g_overlaps):>10.0%}")
    print(f"  {'Same top-1 doc':<30s} {bge_same:>10d}/{len(results)} {g_same:>10d}/{len(results)}")

    # ── Save JSON ──
    results_dir = PROJECT_ROOT / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = results_dir / f"variable_sensitivity_{ts}.json"

    output = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "experiment": "variable_sensitivity_probe",
            "description": (
                "Tests whether swapping sequence variable names (u_n→v_n) "
                "changes retrieval results.  A stable embedding model should "
                "retrieve the same documents regardless of variable letter."
            ),
            "n_pairs": len(QUERY_PAIRS),
            "retrieval_k": k,
            "bge_model": config.EMBEDDING_MODEL_NAME,
            "google_model": "text-embedding-005",
        },
        "aggregate": {
            "bge_m3": {
                "mean_delta": round(float(np.mean(bge_deltas)), 4),
                "max_delta": round(float(np.max(bge_deltas)), 4),
                "mean_top_k_overlap": round(float(np.mean(bge_overlaps)), 2),
                "same_top1_count": bge_same,
            },
            "google": {
                "mean_delta": round(float(np.mean(g_deltas)), 4),
                "max_delta": round(float(np.max(g_deltas)), 4),
                "mean_top_k_overlap": round(float(np.mean(g_overlaps)), 2),
                "same_top1_count": g_same,
            },
        },
        "per_pair": results,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Saved: {out_path}")

    latest = results_dir / "variable_sensitivity_latest.json"
    with open(latest, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {latest}")

    # ── LaTeX table ──
    print_latex(results, bge_deltas, g_deltas, bge_overlaps, g_overlaps,
                bge_same, g_same, k)

    return out_path


def print_latex(results, bge_deltas, g_deltas, bge_overlaps, g_overlaps,
                bge_same, g_same, k):
    """Print a LaTeX-ready table for the thesis."""
    n = len(results)
    print(f"\n\n{'=' * 65}")
    print("  LaTeX table (copy into thesis)")
    print(f"{'=' * 65}")
    print(r"""
\begin{table}[H]
\centering
\caption{Variable-name sensitivity probe. Each row is a query pair
differing only in the sequence variable ($u_n$ vs.\ $v_n$ or $w_n$).
$\Delta d$ is the absolute difference in top-1 L2 distance between the
original and swapped query. Top-3 overlap measures how many of the same
documents are retrieved. Higher overlap and lower $\Delta d$ indicate
greater robustness to superficial notation changes.}
\label{tab:variable-sensitivity}
\small
\begin{tabular}{llrrrr}
\toprule
 & & \multicolumn{2}{c}{\textbf{BGE-M3}} & \multicolumn{2}{c}{\textbf{Google}} \\
\cmidrule(lr){3-4} \cmidrule(lr){5-6}
\textbf{Pair} & \textbf{Topic} & $\Delta d$ & \textbf{Ovlp} & $\Delta d$ & \textbf{Ovlp} \\
\midrule""")

    for r in results:
        bd = r["bge_m3"]["delta"]
        bo = r["bge_m3"]["top_k_overlap"]
        gd = r["google"]["delta"]
        go = r["google"]["top_k_overlap"]
        print(f"{r['pair_id']} & {r['topic']}"
              f" & {bd:.4f} & {bo:.0%}"
              f" & {gd:.4f} & {go:.0%} \\\\")

    print(r"\midrule")
    print(f"\\textbf{{Mean}} & "
          f"& \\textbf{{{np.mean(bge_deltas):.4f}}} & \\textbf{{{np.mean(bge_overlaps):.0%}}}"
          f" & \\textbf{{{np.mean(g_deltas):.4f}}} & \\textbf{{{np.mean(g_overlaps):.0%}}} \\\\")
    print(r"""\bottomrule
\end{tabular}
\end{table}""")

    print(f"\n  Same top-1 document: BGE-M3 {bge_same}/{n}, Google {g_same}/{n}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Variable-name sensitivity probe for embedding models")
    parser.add_argument("--k", type=int, default=3,
                        help="Top-k for retrieval and overlap (default: 3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print query pairs without calling any APIs")
    args = parser.parse_args()
    run_probe(k=args.k, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
